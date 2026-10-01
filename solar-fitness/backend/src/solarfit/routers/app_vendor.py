"""Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

The vendor's own portal — job queue, profile, submissions. Every route
requires role="vendor"; "which vendor am I"
resolves from current_user().vendor_id (karthik's field on the users
row), never from a caller-supplied vendor id.

Response shapes are drilled to match lib/api/client.ts's mock functions
field-for-field (see the vendor.py repository module for the "no
create_job()" gap note) — the intent, per the roadmap, is that swapping
the frontend's mock client for a real fetch call needs no shape changes
on either side.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import Field
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, require_role
from solarfit.db import get_session
from solarfit.providers import manual
from solarfit.providers.validation import GeometryRejected, geometry_confidence
from solarfit.repositories import audit as audit_repo
from solarfit.repositories import notifications as notifications_repo
from solarfit.repositories import sites as sites_repo
from solarfit.repositories import users as users_repo
from solarfit.repositories import vendors as repo
from solarfit.repositories.sites import SiteRow
from solarfit.repositories.vendors import VendorJobRow, VendorPayoutRow, VendorRow
from solarfit.routers.common import CamelModel, actor_audit_fields, request_audit_meta

router = APIRouter(prefix="/app/vendor", tags=["app-vendor"])

VendorJobStatus = Literal[
    "queued", "accepted", "in_progress", "submitted", "sla_at_risk", "overdue", "declined"
]

# In-person survey data (spec sections 3 "Roof Layout/Obstacles" and 7
# "Structural Assessment") — only ever vendor-captured, on-site. See
# repositories/vendors.py's obstacle_survey/structural_assessment column
# docstring for why these are JSONB, not new tables.
ObstacleType = Literal[
    "WATER_TANK",
    "OVERHEAD_TANK",
    "STAIRCASE_ROOM",
    "LIFT_ROOM",
    "SOLAR_WATER_HEATER",
    "EXISTING_SOLAR_PANEL",
    "AC_OUTDOOR_UNIT",
    "PIPE",
    "VENTILATION",
    "ELECTRICAL_EQUIPMENT",
    "ANTENNA",
    "SATELLITE_DISH",
    "CHIMNEY",
    "TREE",
    "ADJACENT_BUILDING",
    "PARAPET_WALL",
    "OTHER",
]

StructuralCondition = Literal["NEW", "GOOD", "AVERAGE", "POOR", "DAMAGED", "UNDER_CONSTRUCTION"]
AssessmentStatus = Literal["pending", "complete", "needs_engineer"]


class ObstacleSurveyItem(CamelModel):
    id: str
    type: ObstacleType
    location: str | None = None
    length_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    distance_from_edge_m: float | None = None
    lat: float | None = None
    lng: float | None = None
    photo_data_url: str | None = None
    notes: str | None = None


class ObstacleSurveyRequest(CamelModel):
    obstacles: list[ObstacleSurveyItem]


class StructuralAssessment(CamelModel):
    roof_structural_type: str | None = None
    rcc_slab_thickness_mm: float | None = None
    structural_condition: StructuralCondition | None = None
    has_cracks: bool | None = None
    has_water_leakage: bool | None = None
    has_corrosion: bool | None = None
    has_structural_damage: bool | None = None
    existing_load_kg_m2: float | None = None
    additional_load_capacity_kg_m2: float | None = None
    recommended_mounting_structure: str | None = None
    inspection_required: bool | None = None
    engineer_approval_required: bool | None = None
    structural_certificate_available: bool | None = None
    structural_certificate_data_url: str | None = None
    assessment_status: AssessmentStatus = "pending"
    estimated_panel_weight_kg: float | None = None
    mounting_structure_weight_kg: float | None = None
    total_additional_load_kg: float | None = None
    load_per_sqm_kg: float | None = None
    roof_load_capacity_kg_m2: float | None = None
    safety_margin_pct: float | None = None
    notes: str | None = None


class ElectricalAssessment(CamelModel):
    """Spec section 8's physical half — only a vendor standing at the
    meter/DB can capture these. The customer-reportable half
    (board/consumer number/connection type/sanctioned load) lives on
    the site instead (set at check creation, see app_checks.py's
    NewCheckInput)."""

    meter_type: str | None = None
    smart_meter: bool | None = None
    net_meter: bool | None = None
    existing_solar_meter: bool | None = None
    meter_location: str | None = None
    meter_photo_data_url: str | None = None
    main_db_location: str | None = None
    main_db_photo_data_url: str | None = None
    db_condition: str | None = None
    available_space: str | None = None
    cable_condition: str | None = None
    earthing_available: bool | None = None
    earthing_condition: str | None = None
    lightning_protection_available: bool | None = None
    notes: str | None = None


class InstallationConstraints(CamelModel):
    """Spec section 12 — entirely vendor-in-person checks (can this crew
    actually get the material and themselves onto this roof)."""

    roof_access_available: bool | None = None
    staircase_available: bool | None = None
    lift_available: bool | None = None
    material_transportation_possible: bool | None = None
    crane_required: bool | None = None
    ladder_access: bool | None = None
    installation_pathway: str | None = None
    roof_entry_permission: bool | None = None
    working_space_available: bool | None = None
    panel_cleaning_access: bool | None = None
    maintenance_access: bool | None = None
    fire_access: bool | None = None
    emergency_access: bool | None = None
    notes: str | None = None


class SafetyAssessment(CamelModel):
    """Spec section 13 — electrical / physical / fire safety, all
    vendor-in-person. Grouped as one flat form matching the spec's own
    three-group structure via field naming, not three nested models —
    it's one page in the field capture UI, not three."""

    # Electrical safety
    proper_earthing: bool | None = None
    lightning_protection: bool | None = None
    surge_protection: bool | None = None
    dc_isolator: bool | None = None
    ac_isolator: bool | None = None
    proper_cable_routing: bool | None = None
    cable_protection: bool | None = None
    electrical_panel_condition: str | None = None
    # Physical safety
    parapet_wall: bool | None = None
    fall_protection: bool | None = None
    safe_roof_access: bool | None = None
    walkway_available: bool | None = None
    panel_maintenance_clearance: bool | None = None
    structural_stability: bool | None = None
    # Fire safety
    fire_risk: Literal["low", "medium", "high"] | None = None
    fire_equipment_available: bool | None = None
    emergency_access: bool | None = None
    inverter_location: str | None = None
    battery_location: str | None = None
    notes: str | None = None


BatteryTechnology = Literal["LITHIUM_ION", "LEAD_ACID", "OTHER"]


class BatteryAssessment(CamelModel):
    """Spec section 14's physical half — battery room/location/
    ventilation/fire safety plus the vendor's own capacity/technology
    recommendation from the actual site. The customer's own interest/
    need (site.battery_required/backup_required/required_backup_hours/
    critical_loads) is a separate, earlier capture at check creation,
    not here."""

    battery_room_available: bool | None = None
    battery_location: str | None = None
    ventilation_available: bool | None = None
    fire_safety_measures: str | None = None
    recommended_battery_capacity_kwh: float | None = None
    recommended_battery_technology: BatteryTechnology | None = None
    notes: str | None = None


# --------------------------------------------------------------------- #
# schemas
# --------------------------------------------------------------------- #


class VendorJobOut(CamelModel):
    id: str
    site_id: str
    site_name: str
    site_type: str
    district: str
    state: str
    deadline: datetime
    payout_inr: float
    status: VendorJobStatus
    assigned_at: datetime
    requirements: list[str]
    distance_km: float | None
    submitted_at: datetime | None = None
    estimated_capacity_kwp: float | None = None
    measured_capacity_kwp: float | None = None
    reconciled_payout_inr: float | None = None
    variance_pct: float | None = None
    dispute_status: Literal["none", "open", "resolved"] | None = None
    dispute_reason: str | None = None
    panorama_photo_data_url: str | None = None
    shading_notes: str | None = None
    obstacle_survey: list[ObstacleSurveyItem] = Field(default_factory=list)
    structural_assessment: StructuralAssessment | None = None
    electrical_assessment: ElectricalAssessment | None = None
    installation_constraints: InstallationConstraints | None = None
    safety_assessment: SafetyAssessment | None = None
    battery_assessment: BatteryAssessment | None = None


class VendorServiceAreaOut(CamelModel):
    region: str
    districts: list[str]


class VendorPayoutMethodOut(CamelModel):
    type: Literal["UPI", "Bank transfer"]
    masked_account: str


class VendorProfileOut(CamelModel):
    vendor_id: str
    name: str
    verification_status: Literal["verified", "pending", "rejected", "suspended"]
    service_area: VendorServiceAreaOut
    availability: bool
    accuracy_score: float
    payout_method: VendorPayoutMethodOut
    documents: list[str]
    joined_at: datetime
    # Settings page's read-only Account Information section. These
    # columns already existed on VendorRow (admin onboarding fields) but
    # were never exposed on this response before — additive, so existing
    # consumers of GET /profile are unaffected.
    legal_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None


class PayoutEntryOut(CamelModel):
    id: str
    job_id: str | None
    amount: float
    status: Literal["pending", "paid", "disputed"]
    date: datetime
    method: Literal["UPI", "Bank transfer"]


class UpdateAvailabilityRequest(CamelModel):
    available: bool


class VendorNotificationPreferencesOut(CamelModel):
    new_job_assignment: bool
    job_deadline_reminders: bool
    job_reassignment: bool
    submission_and_payout_updates: bool
    dispute_updates: bool
    installation_updates: bool


class UpdateNotificationPreferencesRequest(CamelModel):
    new_job_assignment: bool
    job_deadline_reminders: bool
    job_reassignment: bool
    submission_and_payout_updates: bool
    dispute_updates: bool
    installation_updates: bool


class DisputeRequest(CamelModel):
    reason: str = Field(min_length=1)


class PanoramaPhotoRequest(CamelModel):
    data_url: str = Field(min_length=1)


class BoundaryPoint(CamelModel):
    lat: float
    lng: float


class SubmitFieldBoundaryRequest(CamelModel):
    # An open path (the UI's own drawn ring, not yet closed) — same
    # convention app_checks.py's confirmed_boundary uses; closed into a
    # GeoJSON ring server-side, same as _apply_manual_boundary() there.
    points: list[BoundaryPoint] = Field(min_length=3)


class ShadingNotesRequest(CamelModel):
    notes: str = Field(min_length=1)


# --------------------------------------------------------------------- #
# converters
# --------------------------------------------------------------------- #


def _job_out(session: Session, row: VendorJobRow) -> VendorJobOut:
    site = session.get(SiteRow, row.site_id)
    return VendorJobOut(
        id=str(row.id),
        site_id=str(row.site_id),
        site_name=site.name if site else "unknown site",
        site_type=site.site_type if site else "unknown",
        district=row.district,
        state=row.state,
        deadline=row.deadline,
        payout_inr=float(row.payout_inr),
        status=row.status,
        assigned_at=row.created_at,
        requirements=list(row.requirements or []),
        distance_km=row.distance_km,
        submitted_at=row.submitted_at,
        estimated_capacity_kwp=row.estimated_capacity_kwp,
        measured_capacity_kwp=row.measured_capacity_kwp,
        reconciled_payout_inr=float(row.reconciled_payout_inr) if row.reconciled_payout_inr is not None else None,
        variance_pct=row.variance_pct,
        dispute_status=row.dispute_status,
        dispute_reason=row.dispute_reason,
        panorama_photo_data_url=row.panorama_photo_data_url,
        shading_notes=row.shading_notes,
        obstacle_survey=[ObstacleSurveyItem(**o) for o in (row.obstacle_survey or [])],
        structural_assessment=StructuralAssessment(**row.structural_assessment) if row.structural_assessment else None,
        electrical_assessment=ElectricalAssessment(**row.electrical_assessment) if row.electrical_assessment else None,
        installation_constraints=InstallationConstraints(**row.installation_constraints) if row.installation_constraints else None,
        safety_assessment=SafetyAssessment(**row.safety_assessment) if row.safety_assessment else None,
        battery_assessment=BatteryAssessment(**row.battery_assessment) if row.battery_assessment else None,
    )


def _profile_out(row: VendorRow) -> VendorProfileOut:
    return VendorProfileOut(
        vendor_id=str(row.id),
        name=row.name,
        verification_status=row.verification_status,
        service_area=VendorServiceAreaOut(**row.service_area),
        availability=row.availability,
        accuracy_score=row.accuracy_score,
        payout_method=VendorPayoutMethodOut(type=row.payout_method_type, masked_account=row.payout_masked_account),
        documents=list(row.documents or []),
        joined_at=row.joined_at,
        legal_name=row.legal_name,
        contact_phone=row.contact_phone,
        contact_email=row.contact_email,
    )


_DEFAULT_NOTIFICATION_PREFERENCES: dict[str, bool] = {
    "new_job_assignment": True,
    "job_deadline_reminders": True,
    "job_reassignment": True,
    "submission_and_payout_updates": True,
    "dispute_updates": True,
    "installation_updates": True,
}


def _notification_preferences_out(row: VendorRow) -> VendorNotificationPreferencesOut:
    # Merge over the default rather than trusting the stored dict's keys
    # directly — a vendor row created before this column existed reads
    # back as {} until its first PATCH, and should still show every
    # toggle "on" (the migration's own server_default), not a KeyError.
    stored = row.notification_preferences or {}
    merged = {**_DEFAULT_NOTIFICATION_PREFERENCES, **stored}
    return VendorNotificationPreferencesOut(**merged)


def _payout_out(row: VendorPayoutRow) -> PayoutEntryOut:
    return PayoutEntryOut(
        id=str(row.id),
        job_id=str(row.job_id) if row.job_id else None,
        amount=float(row.amount),
        status=row.status,
        date=row.date,
        method=row.method,
    )


def _require_vendor_id(user: AuthenticatedUser) -> str:
    if user.vendor_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no vendor profile linked to this account")
    return user.vendor_id


def _audit_job_action(
    session: Session,
    request: Request,
    user: AuthenticatedUser,
    job: VendorJobRow,
    *,
    action: str,
    details: str,
    previous_value: dict | None = None,
    new_value: dict | None = None,
    reason: str | None = None,
) -> None:
    """Every significant vendor action on a job — spec section 6's
    "Project Activity"/"Technical/Project Work" categories — logged the
    same way, so ~15 call sites on this router don't each hand-build the
    same entity/project/vendor reference. `job.site_id` is the one id
    stable across the whole lifecycle (assessment -> vendor_job ->
    installation all key off it, see app_assessments.py), used as
    project_id the same way the admin-side review endpoints do."""
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(user),
        action=action,
        target=str(job.id),
        details=details,
        entity_type="vendor_job",
        project_id=str(job.site_id),
        vendor_id=str(job.vendor_id) if job.vendor_id else None,
        previous_value=previous_value,
        new_value=new_value,
        reason=reason,
        **request_audit_meta(request),
    )


# --------------------------------------------------------------------- #
# jobs
# --------------------------------------------------------------------- #


@router.get("/jobs", response_model=list[VendorJobOut])
def list_jobs(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
    job_status: Annotated[str | None, Query(alias="status")] = None,
    sort: Annotated[Literal["deadline", "distance", "payout"] | None, Query()] = None,
) -> list[VendorJobOut]:
    vendor_id = _require_vendor_id(user)
    rows = repo.list_jobs(session, vendor_id, status=job_status, sort=sort)
    return [_job_out(session, r) for r in rows]


@router.get("/jobs/{job_id}", response_model=VendorJobOut)
def get_job(
    job_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    vendor_id = _require_vendor_id(user)
    row = _job_or_404(session, job_id, vendor_id)
    # "Project opened/viewed" (spec section 6) — the one read this router
    # audit-logs: it's the point a vendor sees a specific customer's site
    # detail, unlike GET /jobs' list view. Doesn't commit its own
    # transaction (get_session()'s teardown does) since nothing else here
    # writes anything to roll back together with.
    _audit_job_action(
        session, request, user, row, action="vendor_job.viewed", details=f"{user.email} opened job {job_id}"
    )
    session.commit()
    return _job_out(session, row)


def _update_status_or_409(
    session: Session, job_id: str, vendor_id: str, *, status_value: str, **fields: Any
) -> VendorJobRow:
    """Thin adapter: repo.update_job_status() raises ValueError for an
    illegal transition (repositories/vendors.py::VENDOR_JOB_TRANSITIONS) —
    turn that into the same 409 the old per-endpoint _ensure_job_status()
    checks used to raise directly, so a vendor can't e.g. "accept" then
    "decline" a job already in its terminal submitted state, silently
    reverting a completed survey submission (measuredCapacityKwp,
    obstacleSurvey, etc. all still on the row) to "declined"."""
    try:
        row = repo.update_job_status(session, job_id, vendor_id, status=status_value, **fields)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return row


@router.post("/jobs/{job_id}/accept", response_model=VendorJobOut)
def accept_job(
    job_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    vendor_id = _require_vendor_id(user)
    existing = _job_or_404(session, job_id, vendor_id)
    # A plain string snapshot, not a reference — existing and the row
    # _update_status_or_409 returns share the same SQLAlchemy identity, so
    # existing.status would otherwise already read back the NEW value by
    # the time this dict is built.
    previous_status = existing.status
    row = _update_status_or_409(session, job_id, vendor_id, status_value="accepted")
    _audit_job_action(
        session,
        request,
        user,
        row,
        action="vendor_job.accepted",
        details=f"{user.email} accepted job {job_id}",
        previous_value={"status": previous_status},
        new_value={"status": "accepted"},
    )
    session.commit()
    return _job_out(session, row)


@router.post("/jobs/{job_id}/decline", response_model=VendorJobOut)
def decline_job(
    job_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    """Sets status="declined" rather than deleting the row — the job
    stays in this vendor's own history (visible via GET /jobs, same as
    any other past job) AND stays visible to an admin, who can reassign
    it (POST /app/admin/assessments/{id}/reassign) rather than it
    silently disappearing. See repositories/vendors.py::decline_job()'s
    own docstring for why this replaced remove_job() here."""
    vendor_id = _require_vendor_id(user)
    existing = _job_or_404(session, job_id, vendor_id)
    previous_status = existing.status
    try:
        row = repo.decline_job(session, job_id, vendor_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    _audit_job_action(
        session,
        request,
        user,
        row,
        action="vendor_job.declined",
        details=f"{user.email} declined job {job_id}",
        previous_value={"status": previous_status},
        new_value={"status": "declined"},
    )
    # Every admin sees every decline — the same "no per-admin preference"
    # discipline submit_job() below already applies, and a decline needs
    # an admin to reassign the job, so it can't go unnoticed the way a
    # customer-facing notification preference might suppress it.
    for admin_user in users_repo.list_by_role(session, "admin"):
        notifications_repo.create_notification(
            session,
            user_id=admin_user.id,
            kind="job_declined",
            title="A vendor declined a job",
            body=f"Job in {row.district}, {row.state} was declined and needs reassignment.",
        )
    session.commit()
    return _job_out(session, row)


@router.post("/jobs/{job_id}/start", response_model=VendorJobOut)
def start_job(
    job_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    vendor_id = _require_vendor_id(user)
    existing = _job_or_404(session, job_id, vendor_id)
    previous_status = existing.status
    row = _update_status_or_409(session, job_id, vendor_id, status_value="in_progress")
    _audit_job_action(
        session,
        request,
        user,
        row,
        action="vendor_job.site_visit_started",
        details=f"{user.email} started the site visit for job {job_id}",
        previous_value={"status": previous_status},
        new_value={"status": "in_progress"},
    )
    session.commit()
    return _job_out(session, row)


@router.post("/jobs/{job_id}/submit", response_model=VendorJobOut)
def submit_job(
    job_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    vendor_id = _require_vendor_id(user)
    existing = _job_or_404(session, job_id, vendor_id)
    previous_status = existing.status
    row = _update_status_or_409(
        session, job_id, vendor_id, status_value="submitted", submitted_at=datetime.now().astimezone()
    )
    _audit_job_action(
        session,
        request,
        user,
        row,
        action="vendor_job.site_visit_completed",
        details=f"{user.email} submitted the completed survey for job {job_id}",
        previous_value={"status": previous_status},
        new_value={"status": "submitted"},
    )
    # No per-admin notification preference exists (unlike vendors'
    # notification_preferences) — every admin sees every submission.
    for admin_user in users_repo.list_by_role(session, "admin"):
        notifications_repo.create_notification(
            session,
            user_id=admin_user.id,
            kind="job_submitted",
            title="A vendor submitted a survey",
            body=f"Job in {existing.district}, {existing.state} was submitted.",
        )
    session.commit()
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/panorama", response_model=VendorJobOut)
def upload_panorama_photo(
    job_id: str,
    payload: PanoramaPhotoRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.set_panorama_photo(session, job_id, vendor_id, data_url=payload.data_url)
    _audit_job_action(
        session, request, user, row, action="vendor_job.site_photo_uploaded",
        details=f"{user.email} uploaded a site panorama photo for job {job_id}",
    )
    session.commit()
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/boundary", response_model=VendorJobOut)
def submit_field_boundary(
    job_id: str,
    payload: SubmitFieldBoundaryRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    """GEO-02/SITE-05, the vendor side of a manually-drawn boundary. The
    vendor's own on-site trace, tagged `field_measured` — GEO-09's
    highest-trust geometry source (base confidence 0.95, and immune to
    the imagery-age penalty other sources take, since a person physically
    at the building isn't reading a satellite photo) — rather than
    `manual_polygon` (0.75), which app_checks.py::_apply_manual_boundary()
    already owns for a customer's own desk-bound edit. Shares that same
    validate-then-version pipeline; only the source/confidence differ.
    """
    vendor_id = _require_vendor_id(user)
    row = _job_or_404(session, job_id, vendor_id)

    site = sites_repo.get(session, str(row.site_id))
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "site not found")

    boundary_geojson = {
        "type": "Polygon",
        # A GeoJSON ring must close; the UI sends the open path it drew.
        "coordinates": [
            [[p.lng, p.lat] for p in payload.points] + [[payload.points[0].lng, payload.points[0].lat]]
        ],
    }
    try:
        validated = manual.resolve_manual(site, {"boundary": boundary_geojson})
    except GeometryRejected as exc:
        # A self-intersecting or degenerate trace is the vendor's input
        # to fix on-site, not a server fault — never silently repaired.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    confidence = geometry_confidence(source="field_measured", imagery_date=site.imagery_date, boundary=validated)

    sites_repo.new_geometry_version(
        session,
        str(row.site_id),
        boundary=validated,
        actor=user.email,
        source="vendor_field_survey",
        geometry_source="field_measured",
        geometry_confidence=confidence,
    )
    _audit_job_action(
        session, request, user, row, action="vendor_job.boundary_captured",
        details=f"{user.email} captured a field-measured boundary ({len(payload.points)} points) for job {job_id}",
        new_value={"points": len(payload.points)},
    )
    session.commit()
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/shading-notes", response_model=VendorJobOut)
def save_shading_notes(
    job_id: str,
    payload: ShadingNotesRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.set_shading_notes(session, job_id, vendor_id, notes=payload.notes)
    _audit_job_action(
        session, request, user, row, action="vendor_job.shading_notes_updated",
        details=f"{user.email} updated shading notes for job {job_id}",
    )
    session.commit()
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/obstacles", response_model=VendorJobOut)
def save_obstacle_survey(
    job_id: str,
    payload: ObstacleSurveyRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    """Replaces the job's whole obstacle list — the field capture UI
    (spec section 3) sends its current set on every save, same
    replace-not-patch semantics every other single-value job field on
    this router already uses."""
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.set_obstacle_survey(
        session, job_id, vendor_id, obstacles=[o.model_dump(by_alias=False) for o in payload.obstacles]
    )
    _audit_job_action(
        session, request, user, row, action="vendor_job.obstacle_survey_updated",
        details=f"{user.email} saved {len(payload.obstacles)} obstacle(s) for job {job_id}",
    )
    session.commit()
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/structural-assessment", response_model=VendorJobOut)
def save_structural_assessment(
    job_id: str,
    payload: StructuralAssessment,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    """Spec section 7. One assessment per job, replaced wholesale on
    every save — the field form is a single page, not a series of
    incremental patches."""
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.set_structural_assessment(session, job_id, vendor_id, assessment=payload.model_dump(by_alias=False))
    _audit_job_action(
        session, request, user, row, action="vendor_job.structural_assessment_updated",
        details=f"{user.email} saved the structural assessment for job {job_id}",
    )
    session.commit()
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/electrical-assessment", response_model=VendorJobOut)
def save_electrical_assessment(
    job_id: str,
    payload: ElectricalAssessment,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    """Spec section 8's physical half. One assessment per job, replaced
    wholesale on every save — same convention as
    save_structural_assessment() above."""
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.set_electrical_assessment(session, job_id, vendor_id, assessment=payload.model_dump(by_alias=False))
    _audit_job_action(
        session, request, user, row, action="vendor_job.electrical_assessment_updated",
        details=f"{user.email} saved the electrical assessment for job {job_id}",
    )
    session.commit()
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/installation-constraints", response_model=VendorJobOut)
def save_installation_constraints(
    job_id: str,
    payload: InstallationConstraints,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    """Spec section 12. One record per job, replaced wholesale on every
    save — same convention as every other assessment on this router."""
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.set_installation_constraints(session, job_id, vendor_id, constraints=payload.model_dump(by_alias=False))
    _audit_job_action(
        session, request, user, row, action="vendor_job.installation_constraints_updated",
        details=f"{user.email} saved installation constraints for job {job_id}",
    )
    session.commit()
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/safety-assessment", response_model=VendorJobOut)
def save_safety_assessment(
    job_id: str,
    payload: SafetyAssessment,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    """Spec section 13."""
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.set_safety_assessment(session, job_id, vendor_id, assessment=payload.model_dump(by_alias=False))
    _audit_job_action(
        session, request, user, row, action="vendor_job.safety_assessment_updated",
        details=f"{user.email} saved the safety assessment for job {job_id}",
    )
    session.commit()
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/battery-assessment", response_model=VendorJobOut)
def save_battery_assessment(
    job_id: str,
    payload: BatteryAssessment,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    """Spec section 14's physical half."""
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.set_battery_assessment(session, job_id, vendor_id, assessment=payload.model_dump(by_alias=False))
    _audit_job_action(
        session, request, user, row, action="vendor_job.battery_assessment_updated",
        details=f"{user.email} saved the battery assessment for job {job_id}",
    )
    session.commit()
    return _job_out(session, row)


def _job_or_404(session: Session, job_id: str, vendor_id: str) -> VendorJobRow:
    try:
        row = repo.get_job(session, job_id, vendor_id)
    except ValueError as exc:  # malformed UUID
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found") from exc
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return row


# --------------------------------------------------------------------- #
# profile
# --------------------------------------------------------------------- #


@router.get("/profile", response_model=VendorProfileOut)
def get_profile(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorProfileOut:
    vendor_id = _require_vendor_id(user)
    row = _vendor_or_404(session, vendor_id)
    return _profile_out(row)


@router.patch("/profile/availability", response_model=VendorProfileOut)
def update_availability(
    payload: UpdateAvailabilityRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorProfileOut:
    vendor_id = _require_vendor_id(user)
    _vendor_or_404(session, vendor_id)
    row = repo.update_availability(session, vendor_id, payload.available)
    return _profile_out(row)


@router.get("/profile/notification-preferences", response_model=VendorNotificationPreferencesOut)
def get_notification_preferences(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorNotificationPreferencesOut:
    vendor_id = _require_vendor_id(user)
    row = _vendor_or_404(session, vendor_id)
    return _notification_preferences_out(row)


@router.patch("/profile/notification-preferences", response_model=VendorNotificationPreferencesOut)
def update_notification_preferences(
    payload: UpdateNotificationPreferencesRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorNotificationPreferencesOut:
    vendor_id = _require_vendor_id(user)
    _vendor_or_404(session, vendor_id)
    row = repo.update_notification_preferences(session, vendor_id, payload.model_dump())
    return _notification_preferences_out(row)


def _vendor_or_404(session: Session, vendor_id: str) -> VendorRow:
    try:
        row = repo.get_vendor(session, vendor_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found") from exc
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    return row


# --------------------------------------------------------------------- #
# submissions
#
# Note: vendor-facing /payouts and /earnings-summary routes were removed
# (earnings feature removed from the vendor portal). PayoutEntryOut and
# _payout_out() stay defined here — routers/app_admin_vendors.py still
# imports both for its own GET /admin/vendors/{id}/payouts, which is a
# separate (admin-facing) feature and was not touched.
# --------------------------------------------------------------------- #


@router.get("/submissions", response_model=list[VendorJobOut])
def list_submissions(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> list[VendorJobOut]:
    vendor_id = _require_vendor_id(user)
    return [_job_out(session, r) for r in repo.list_submissions(session, vendor_id)]


@router.post("/submissions/{job_id}/dispute", response_model=VendorJobOut)
def dispute_submission(
    job_id: str,
    payload: DisputeRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.dispute_job(session, job_id, vendor_id, reason=payload.reason)
    _audit_job_action(
        session, request, user, row, action="vendor_job.disputed",
        details=f"{user.email} disputed the payout for job {job_id}: {payload.reason}",
        reason=payload.reason,
    )
    session.commit()
    return _job_out(session, row)
