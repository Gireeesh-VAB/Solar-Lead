"""Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

The vendor's own portal — job queue, profile, payouts, earnings,
submissions. Every route requires role="vendor"; "which vendor am I"
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
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, require_role
from solarfit.db import get_session
from solarfit.repositories import vendors as repo
from solarfit.repositories.sites import SiteRow
from solarfit.repositories.vendors import VendorJobRow, VendorPayoutRow, VendorRow
from solarfit.routers.common import CamelModel

router = APIRouter(prefix="/app/vendor", tags=["app-vendor"])

VendorJobStatus = Literal["queued", "accepted", "in_progress", "submitted", "sla_at_risk", "overdue"]

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


class VendorAccuracyPointOut(CamelModel):
    label: str
    score: float


class VendorProfileOut(CamelModel):
    vendor_id: str
    name: str
    verification_status: Literal["verified", "pending", "rejected", "suspended"]
    service_area: VendorServiceAreaOut
    availability: bool
    accuracy_score: float
    accuracy_trend: list[VendorAccuracyPointOut]
    payout_method: VendorPayoutMethodOut
    documents: list[str]
    joined_at: datetime


class PayoutEntryOut(CamelModel):
    id: str
    job_id: str | None
    amount: float
    status: Literal["pending", "paid", "disputed"]
    date: datetime
    method: Literal["UPI", "Bank transfer"]


class VendorEarningsSummaryOut(CamelModel):
    week_total_inr: float
    pending_inr: float
    paid_inr: float
    disputed_inr: float
    jobs_completed_this_week: int


class UpdateAvailabilityRequest(CamelModel):
    available: bool


class DisputeRequest(CamelModel):
    reason: str = Field(min_length=1)


class PanoramaPhotoRequest(CamelModel):
    data_url: str = Field(min_length=1)


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


def _profile_out(row: VendorRow, history: list) -> VendorProfileOut:
    accuracy_trend = [VendorAccuracyPointOut(label=h.label, score=h.score) for h in history]
    return VendorProfileOut(
        vendor_id=str(row.id),
        name=row.name,
        verification_status=row.verification_status,
        service_area=VendorServiceAreaOut(**row.service_area),
        availability=row.availability,
        accuracy_score=row.accuracy_score,
        accuracy_trend=accuracy_trend,
        payout_method=VendorPayoutMethodOut(type=row.payout_method_type, masked_account=row.payout_masked_account),
        documents=list(row.documents or []),
        joined_at=row.joined_at,
    )


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
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    vendor_id = _require_vendor_id(user)
    row = _job_or_404(session, job_id, vendor_id)
    return _job_out(session, row)


@router.post("/jobs/{job_id}/accept", response_model=VendorJobOut)
def accept_job(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.update_job_status(session, job_id, vendor_id, status="accepted")
    return _job_out(session, row)


@router.post("/jobs/{job_id}/decline", response_model=VendorJobOut)
def decline_job(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    """Matches lib/api/client.ts's real semantics: declining removes the
    job from the vendor's queue entirely, not just a status flip — the
    response still describes the job as it was right before removal."""
    vendor_id = _require_vendor_id(user)
    row = _job_or_404(session, job_id, vendor_id)
    out = _job_out(session, row)
    repo.remove_job(session, job_id, vendor_id)
    return out


@router.post("/jobs/{job_id}/start", response_model=VendorJobOut)
def start_job(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.update_job_status(session, job_id, vendor_id, status="in_progress")
    return _job_out(session, row)


@router.post("/jobs/{job_id}/submit", response_model=VendorJobOut)
def submit_job(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.update_job_status(
        session, job_id, vendor_id, status="submitted", submitted_at=datetime.now().astimezone()
    )
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/panorama", response_model=VendorJobOut)
def upload_panorama_photo(
    job_id: str,
    payload: PanoramaPhotoRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.set_panorama_photo(session, job_id, vendor_id, data_url=payload.data_url)
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/shading-notes", response_model=VendorJobOut)
def save_shading_notes(
    job_id: str,
    payload: ShadingNotesRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.set_shading_notes(session, job_id, vendor_id, notes=payload.notes)
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/obstacles", response_model=VendorJobOut)
def save_obstacle_survey(
    job_id: str,
    payload: ObstacleSurveyRequest,
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
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/structural-assessment", response_model=VendorJobOut)
def save_structural_assessment(
    job_id: str,
    payload: StructuralAssessment,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    """Spec section 7. One assessment per job, replaced wholesale on
    every save — the field form is a single page, not a series of
    incremental patches."""
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.set_structural_assessment(session, job_id, vendor_id, assessment=payload.model_dump(by_alias=False))
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/electrical-assessment", response_model=VendorJobOut)
def save_electrical_assessment(
    job_id: str,
    payload: ElectricalAssessment,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    """Spec section 8's physical half. One assessment per job, replaced
    wholesale on every save — same convention as
    save_structural_assessment() above."""
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.set_electrical_assessment(session, job_id, vendor_id, assessment=payload.model_dump(by_alias=False))
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/installation-constraints", response_model=VendorJobOut)
def save_installation_constraints(
    job_id: str,
    payload: InstallationConstraints,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    """Spec section 12. One record per job, replaced wholesale on every
    save — same convention as every other assessment on this router."""
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.set_installation_constraints(session, job_id, vendor_id, constraints=payload.model_dump(by_alias=False))
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/safety-assessment", response_model=VendorJobOut)
def save_safety_assessment(
    job_id: str,
    payload: SafetyAssessment,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    """Spec section 13."""
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.set_safety_assessment(session, job_id, vendor_id, assessment=payload.model_dump(by_alias=False))
    return _job_out(session, row)


@router.patch("/jobs/{job_id}/battery-assessment", response_model=VendorJobOut)
def save_battery_assessment(
    job_id: str,
    payload: BatteryAssessment,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    """Spec section 14's physical half."""
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.set_battery_assessment(session, job_id, vendor_id, assessment=payload.model_dump(by_alias=False))
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
    return _profile_out_with_history(session, row)


@router.patch("/profile/availability", response_model=VendorProfileOut)
def update_availability(
    payload: UpdateAvailabilityRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorProfileOut:
    vendor_id = _require_vendor_id(user)
    _vendor_or_404(session, vendor_id)
    row = repo.update_availability(session, vendor_id, payload.available)
    return _profile_out_with_history(session, row)


def _vendor_or_404(session: Session, vendor_id: str) -> VendorRow:
    try:
        row = repo.get_vendor(session, vendor_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found") from exc
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    return row


def _profile_out_with_history(session: Session, row: VendorRow) -> VendorProfileOut:
    history = repo.get_accuracy_history(session, str(row.id))
    return _profile_out(row, history)


# --------------------------------------------------------------------- #
# payouts / earnings / submissions
# --------------------------------------------------------------------- #


@router.get("/payouts", response_model=list[PayoutEntryOut])
def list_payouts(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> list[PayoutEntryOut]:
    vendor_id = _require_vendor_id(user)
    return [_payout_out(r) for r in repo.list_payouts(session, vendor_id)]


@router.get("/earnings-summary", response_model=VendorEarningsSummaryOut)
def get_earnings_summary(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorEarningsSummaryOut:
    vendor_id = _require_vendor_id(user)
    summary = repo.get_earnings_summary(session, vendor_id)
    return VendorEarningsSummaryOut(**summary)


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
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> VendorJobOut:
    vendor_id = _require_vendor_id(user)
    _job_or_404(session, job_id, vendor_id)
    row = repo.dispute_job(session, job_id, vendor_id, reason=payload.reason)
    return _job_out(session, row)
