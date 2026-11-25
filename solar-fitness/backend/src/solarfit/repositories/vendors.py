"""Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

The vendor portal's data layer: a vendor's own profile, the jobs queued
or assigned to them, their payouts, and their accuracy-over-time
history. Mirrors repositories/users.py's shape (plain ORM row classes +
module-level functions taking `session` first) rather than sites.py's
heavier domain-model-conversion pattern — none of this needs PostGIS or
a frozen cross-team contract, it's plain CRUD behind the vendor's own
portal.

Every "which vendor am I" scoping check happens one layer up, in the
router, via current_user().vendor_id — these functions take vendor_id
as an explicit parameter and never trust a caller-supplied one.

create_job() is the one populating path for vendor_jobs today: routers/
app_assessments.py::approve_assessment() creates it once an admin has
approved the enquiry and chosen a vendor — the feasibility check itself
(routers/app_checks.py::complete_check()) never creates a job directly;
completing a check only computes an assessment, and the customer's own
routers/app_checks.py::raise_enquiry() endpoint is what turns that into
something an admin sees, still with no vendor_jobs row until approval.
Every other write in this module still takes an existing job/vendor id
— create_job() is the only one that creates a vendor_jobs row from
scratch. Tests otherwise seed rows directly against these ORM classes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base
from solarfit.repositories import notifications as notifications_repo
from solarfit.repositories import users as users_repo

__all__ = [
    "VENDOR_JOB_TRANSITIONS",
    "VendorAccuracyHistoryRow",
    "VendorJobRow",
    "VendorPayoutRow",
    "VendorRow",
    "best_available_vendor_for_district",
    "count_active_jobs_for_sites",
    "create_job",
    "create_vendor",
    "decline_job",
    "dispute_job",
    "get_job",
    "get_latest_job_for_site",
    "get_vendor",
    "list_jobs",
    "list_payouts",
    "list_submissions",
    "list_vendors",
    "notify_vendor_users",
    "remove_job",
    "set_battery_assessment",
    "set_electrical_assessment",
    "set_installation_constraints",
    "set_obstacle_survey",
    "set_panorama_photo",
    "set_safety_assessment",
    "set_shading_notes",
    "set_structural_assessment",
    "set_verification_status",
    "sweep_vendor_job_sla",
    "update_availability",
    "update_job_status",
    "update_notification_preferences",
    "vendor_admin_stats",
    "vendor_has_job_for_site",
]


class VendorRow(Base):
    """A vendor's own profile — one row per vendor, referenced from
    users.vendor_id (the login) and from vendor_jobs/vendor_payouts/
    vendor_accuracy_history (the work)."""

    __tablename__ = "vendors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    availability: Mapped[bool] = mapped_column(nullable=False, default=True)
    accuracy_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    service_area: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {region, districts:[]}
    payout_method_type: Mapped[str] = mapped_column(String(16), nullable=False)  # UPI | Bank transfer
    payout_masked_account: Mapped[str] = mapped_column(String(64), nullable=False)
    documents: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Onboarding/profile fields — added alongside the admin "Add Vendor"
    # flow (create_vendor() below). All nullable: existing vendor rows
    # predate these and are never backfilled.
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gst_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pan_number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    certifications: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Settings page — six independent toggles as one dict, same
    # convention as service_area above, rather than six columns.
    notification_preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class VendorJobRow(Base):
    """A survey job, queued or assigned. district/state are stored
    directly here (denormalized) rather than read from sites — sites has
    no district/state columns yet, and this table shouldn't have to wait
    on that separate, unrelated workstream landing first."""

    __tablename__ = "vendor_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    district: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(255), nullable=False)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payout_inr: Mapped[Any] = mapped_column(Numeric(), nullable=False)
    requirements: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    distance_km: Mapped[float | None] = mapped_column(nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_capacity_kwp: Mapped[float | None] = mapped_column(nullable=True)
    measured_capacity_kwp: Mapped[float | None] = mapped_column(nullable=True)
    reconciled_payout_inr: Mapped[Any | None] = mapped_column(Numeric(), nullable=True)
    variance_pct: Mapped[float | None] = mapped_column(nullable=True)
    dispute_status: Mapped[str | None] = mapped_column(String(16), nullable=True, default="none")
    dispute_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    panorama_photo_data_url: Mapped[str | None] = mapped_column(Text(), nullable=True)
    shading_notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # In-person survey data (spec sections 3 "Roof Layout/Obstacles" and 7
    # "Structural Assessment") — only a vendor standing on the roof can
    # capture these, so they live on the job, not the site, and are only
    # ever written through the vendor's own capture endpoints
    # (routers/app_vendor.py's set_obstacle_survey/set_structural_assessment).
    # JSONB rather than new tables — same tradeoff this schema already
    # makes for requirements/service_area/documents/capacity/vision_refinement:
    # each item's shape is this feature's own concern, not a cross-team
    # frozen contract, so it doesn't need a normalized table + migration
    # every time a field is added.
    obstacle_survey: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    structural_assessment: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Spec section 8's physical half (meter/DB photos, earthing, lightning
    # protection) — the customer-reportable half (board/consumer number/
    # sanctioned load) lives on sites instead, set at check creation.
    electrical_assessment: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Spec sections 12 "Installation Constraints" and 13 "Safety
    # Assessment" — both entirely vendor-in-person checks, same pattern.
    installation_constraints: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    safety_assessment: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Spec section 14's physical half — battery room/location/
    # ventilation/fire safety plus the vendor's own capacity/technology
    # recommendation from the actual site. The customer's own interest/
    # need (battery_required/backup_required/required_backup_hours/
    # critical_loads) lives on sites instead.
    battery_assessment: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Lead-passing history — every vendor_id this job has already been
    # offered to and lost (via sweep_vendor_job_sla()'s reassignment),
    # stored as strings since JSONB can't hold UUID objects directly.
    # Read back as str, not uuid.UUID — callers compare against
    # str(vendor.id). Never includes the CURRENT vendor_id, only past
    # ones; a job that has never been reassigned has an empty list.
    previous_vendor_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class VendorPayoutRow(Base):
    __tablename__ = "vendor_payouts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_jobs.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Any] = mapped_column(Numeric(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # pending | paid | disputed
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)  # UPI | Bank transfer


# Nothing reads this table anymore — get_accuracy_history() was removed
# along with the vendor portal's Performance feature (the only consumer
# of the accuracy trend it backed). Kept, unlike the removed function,
# since dropping the table is a separate, more destructive migration this
# removal didn't ask for.
class VendorAccuracyHistoryRow(Base):
    __tablename__ = "vendor_accuracy_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# --------------------------------------------------------------------- #
# vendor profile
# --------------------------------------------------------------------- #


def create_vendor(
    session: Session,
    *,
    name: str,
    payout_method_type: str,
    payout_masked_account: str,
    service_area: dict | None = None,
    documents: list | None = None,
    certifications: list | None = None,
    **extra: Any,
) -> VendorRow:
    """Admin "Add Vendor" flow — the one populating path for the vendors
    table. Raises sqlalchemy.exc.IntegrityError on constraint violations;
    the router's job to catch and turn into an HTTP response, same
    convention as repositories/users.py::create_user()."""
    row = VendorRow(
        name=name,
        payout_method_type=payout_method_type,
        payout_masked_account=payout_masked_account,
        service_area=service_area or {},
        documents=documents or [],
        certifications=certifications or [],
        **extra,
    )
    session.add(row)
    session.flush()
    return row


def get_vendor(session: Session, vendor_id: str | uuid.UUID) -> VendorRow | None:
    return session.get(VendorRow, uuid.UUID(str(vendor_id)))


def list_vendors(
    session: Session,
    *,
    q: str | None = None,
    verification_status: str | None = None,
    sort: str | None = None,
) -> list[VendorRow]:
    """Admin listing — every vendor, unscoped (contrast with list_jobs()
    etc. above, which are always scoped to one vendor's own portal).
    `q` matches name or service_area.region, case-insensitively; filtered
    in Python since the vendor base is a per-deployment admin list, not
    consumer-scale, same tradeoff repositories/customer_accounts.py's
    list_tenants() already makes."""
    stmt = select(VendorRow)
    if verification_status is not None:
        stmt = stmt.where(VendorRow.verification_status == verification_status)
    rows = list(session.scalars(stmt))

    if q:
        needle = q.lower()
        rows = [
            r
            for r in rows
            if needle in r.name.lower() or needle in str(r.service_area.get("region", "")).lower()
        ]
    if sort == "accuracy":
        rows.sort(key=lambda r: r.accuracy_score, reverse=True)
    elif sort == "sla":
        rows.sort(key=lambda r: vendor_admin_stats(session, r.id)["sla_compliance_pct"], reverse=True)
    return rows


def set_verification_status(session: Session, vendor_id: str | uuid.UUID, status: str) -> VendorRow | None:
    """Admin action — suspend/reinstate/approve/reject all funnel through
    this one status write. verification_status is the single source of
    truth for a vendor's standing; there's no separate "suspended" flag
    to keep in sync."""
    row = get_vendor(session, vendor_id)
    if row is not None:
        row.verification_status = status
        session.flush()
    return row


def notify_vendor_users(
    session: Session,
    vendor_id: str | uuid.UUID,
    *,
    preference_key: str,
    kind: str,
    title: str,
    body: str | None = None,
) -> None:
    """Writes an in-app notification (repositories/notifications.py) to
    every login belonging to this vendor — the vendor's own account plus
    any sub-users (repositories/users.py::list_by_vendor_id) — gated by
    that vendor's own notification_preferences toggle. Missing from the
    stored dict defaults to on, same "fail open" default
    app_vendor.py::_notification_preferences_out()'s merge already
    uses for a never-configured vendor."""
    vendor_row = get_vendor(session, vendor_id)
    if vendor_row is None:
        return
    if not (vendor_row.notification_preferences or {}).get(preference_key, True):
        return
    for user in users_repo.list_by_vendor_id(session, vendor_id):
        notifications_repo.create_notification(session, user_id=user.id, kind=kind, title=title, body=body)


def count_active_jobs_for_sites(session: Session, site_ids: list[str]) -> int:
    """Closes a real gap found during a frontend/backend sync audit:
    PortfolioSummary.activeJobs was stubbed to 0 with a "once
    vendor_jobs lands" TODO — it landed with keerthana's merge. "Active"
    matches vendor_admin_stats()'s own definition: everything not yet
    submitted."""
    if not site_ids:
        return 0
    site_uuids = [uuid.UUID(str(s)) for s in site_ids]
    stmt = select(VendorJobRow).where(
        VendorJobRow.site_id.in_(site_uuids), VendorJobRow.status.not_in(["submitted", "declined"])
    )
    return len(list(session.scalars(stmt)))


def vendor_admin_stats(session: Session, vendor_id: str | uuid.UUID) -> dict[str, Any]:
    """activeJobs/totalJobsCompleted/slaCompliancePct — computed at read
    time from vendor_jobs, never stored, so they can't drift from the
    real job history. "Completed" = submitted; "active" = everything
    else except a declined job (queued/accepted/in_progress/sla_at_risk/
    overdue) — a decline is a closed, not an open, matter for this
    vendor. SLA compliance = the fraction of submitted jobs turned in at
    or before their deadline — an honest 0.0 (not a fabricated number) when
    nothing has been submitted yet."""
    vid = uuid.UUID(str(vendor_id))
    rows = list(session.scalars(select(VendorJobRow).where(VendorJobRow.vendor_id == vid)))

    submitted = [r for r in rows if r.status == "submitted"]
    active = [r for r in rows if r.status not in ("submitted", "declined")]
    on_time = [r for r in submitted if r.submitted_at is not None and r.submitted_at <= r.deadline]

    return {
        "active_jobs": len(active),
        "total_jobs_completed": len(submitted),
        "sla_compliance_pct": (len(on_time) / len(submitted) * 100.0) if submitted else 0.0,
    }


def update_availability(session: Session, vendor_id: str | uuid.UUID, available: bool) -> VendorRow | None:
    row = get_vendor(session, vendor_id)
    if row is not None:
        row.availability = available
        session.flush()
    return row


def update_notification_preferences(
    session: Session, vendor_id: str | uuid.UUID, preferences: dict
) -> VendorRow | None:
    row = get_vendor(session, vendor_id)
    if row is not None:
        row.notification_preferences = preferences
        session.flush()
    return row


# --------------------------------------------------------------------- #
# jobs
# --------------------------------------------------------------------- #


# Survey-job defaults — shared by routers/app_assessments.py's admin
# approve_assessment() (the only place a vendor_jobs row gets created now;
# see that router's module docstring for why this moved out of
# routers/app_checks.py::complete_check()).
_BOUNDARY_REQ = "Capture boundary polygon"
_USN_REQ = "Confirm USN via bill OCR"
_PANORAMA_REQ = "Upload panorama photo"
_SHADING_REQ = "Note shading obstructions"
DEFAULT_SURVEY_DEADLINE_DAYS = 3
MIN_SURVEY_PAYOUT_INR = 800
PAYOUT_PER_KWP_INR = 350


def default_survey_requirements(site_type: str) -> list[str]:
    from solarfit.domain.site import BILLING_LINKED_SITE_TYPES

    requirements = [_BOUNDARY_REQ, _PANORAMA_REQ]
    if site_type in BILLING_LINKED_SITE_TYPES:
        requirements.append(_USN_REQ)
    requirements.append(_SHADING_REQ)
    return requirements


def default_survey_payout_inr(estimated_capacity_kwp: float | None) -> float:
    return max(MIN_SURVEY_PAYOUT_INR, round((estimated_capacity_kwp or 3) * PAYOUT_PER_KWP_INR))


def create_job(
    session: Session,
    *,
    site_id: str | uuid.UUID,
    district: str,
    state: str,
    requirements: list[str],
    payout_inr: float,
    estimated_capacity_kwp: float | None,
    deadline: datetime,
    vendor_id: str | uuid.UUID | None = None,
    status: str = "queued",
) -> VendorJobRow:
    """Creates a survey job. vendor_id=None (the default) was historically
    "unassigned, pick this up later" but nothing ever implemented that
    pickup path — GET /app/vendor/jobs only ever returns jobs already
    scoped to the caller's own vendor_id, so an unassigned row was
    permanently invisible. routers/app_assessments.py's approve_assessment()
    is now the only caller that matters in practice, and it always passes
    a real vendor_id (the admin's explicit choice) so the row is visible
    to that vendor immediately."""
    row = VendorJobRow(
        site_id=uuid.UUID(str(site_id)),
        vendor_id=uuid.UUID(str(vendor_id)) if vendor_id is not None else None,
        status=status,
        district=district,
        state=state,
        deadline=deadline,
        payout_inr=payout_inr,
        requirements=requirements,
        estimated_capacity_kwp=estimated_capacity_kwp,
    )
    session.add(row)
    session.flush()
    return row


def list_jobs(
    session: Session,
    vendor_id: str | uuid.UUID,
    *,
    status: str | None = None,
    sort: str | None = None,
) -> list[VendorJobRow]:
    stmt = select(VendorJobRow).where(VendorJobRow.vendor_id == uuid.UUID(str(vendor_id)))
    if status is not None:
        stmt = stmt.where(VendorJobRow.status == status)
    if sort == "deadline":
        stmt = stmt.order_by(VendorJobRow.deadline)
    elif sort == "distance":
        stmt = stmt.order_by(VendorJobRow.distance_km)
    elif sort == "payout":
        stmt = stmt.order_by(VendorJobRow.payout_inr.desc())
    else:
        stmt = stmt.order_by(VendorJobRow.deadline)
    return list(session.scalars(stmt))


def vendor_has_job_for_site(session: Session, vendor_id: str | uuid.UUID, site_id: str | uuid.UUID) -> bool:
    """GET /app/sites/{id} is owner_org-scoped (a vendor has none) — this
    is the narrow exception that lets a vendor read the one site they
    actually have an assigned job on, without opening site reads up to
    every vendor for every site."""
    stmt = select(VendorJobRow.id).where(
        VendorJobRow.vendor_id == uuid.UUID(str(vendor_id)), VendorJobRow.site_id == uuid.UUID(str(site_id))
    )
    return session.scalars(stmt).first() is not None


def get_latest_job_for_site(session: Session, site_id: str | uuid.UUID) -> VendorJobRow | None:
    """The customer-facing "has a vendor been assigned to my roof, and
    where are they in the process" lookup — unlike get_job() above, this
    is scoped by site, not vendor, since the caller here is the
    customer's own check page, not a vendor's portal. Most recent job
    wins (a site can in principle accumulate more than one job across
    separate review cycles); returns None when no survey has ever been
    queued for this site, same "absence is data" discipline as
    everywhere else this codebase surfaces optional state."""
    stmt = (
        select(VendorJobRow)
        .where(VendorJobRow.site_id == uuid.UUID(str(site_id)))
        .order_by(VendorJobRow.created_at.desc())
    )
    return session.scalars(stmt).first()


def get_job(session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID) -> VendorJobRow | None:
    """Scoped to vendor_id — a job assigned to someone else is treated as
    not found, the same not-403 reasoning routers/sites.py's
    _owned_or_404 already uses (a 403 would confirm the id exists)."""
    row = session.get(VendorJobRow, uuid.UUID(str(job_id)))
    if row is None or row.vendor_id != uuid.UUID(str(vendor_id)):
        return None
    return row


# Which vendor-initiated status moves are legal from a job's current status.
# Formalizes what routers/app_vendor.py's per-endpoint _ensure_job_status()
# checks used to enforce ad hoc for accept/decline/start, and closes the one
# transition that check never covered at all: submit_job() had no guard
# before this, so a declined or already-submitted job could be
# re-"submitted" over its real terminal state. "submitted": {"submitted"} is
# an identity transition, not a real move — it's what dispute_job() below
# needs (re-flagging an already-submitted job with dispute fields set,
# without changing its status). sla_at_risk/overdue are the SLA sweep's own
# statuses (repositories/vendors.py::sweep_vendor_job_sla) — that function
# writes row.status directly rather than through this table, so it never
# needs an entry here; jobs it marks just need a way back to "submitted"
# once the vendor finishes the now-late work.
VENDOR_JOB_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"accepted", "declined", "in_progress", "submitted"},
    "accepted": {"in_progress", "declined", "submitted"},
    "in_progress": {"submitted"},
    # sla_at_risk/overdue can land on a job that was already "in_progress"
    # (sweep_vendor_job_sla() above sweeps queued/accepted/in_progress
    # alike) OR one that's still "accepted" and was simply never started
    # before its deadline pressure kicked in — the SLA sweep collapses
    # both into the same status literal. "submitted" alone covered the
    # former; it silently locked the latter out of ever starting at all
    # (POST /jobs/{id}/start would 409 forever, with no way back). Per
    # this function's own docstring — "accepted work in progress is
    # never yanked away" — a late-but-still-owned job stays the vendor's
    # to work, so both directions must stay open here.
    "sla_at_risk": {"in_progress", "submitted"},
    "overdue": {"in_progress", "submitted"},
    "submitted": {"submitted"},
    "declined": set(),
}


def update_job_status(
    session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID, *, status: str, **fields: Any
) -> VendorJobRow | None:
    """Raises ValueError when `status` isn't a transition
    VENDOR_JOB_TRANSITIONS allows from the job's current status —
    routers/app_vendor.py turns that into a 409, same convention the old
    per-endpoint _ensure_job_status() checks already used."""
    row = get_job(session, job_id, vendor_id)
    if row is None:
        return None
    if status not in VENDOR_JOB_TRANSITIONS.get(row.status, set()):
        raise ValueError(f"job is {row.status}, cannot transition to {status}")
    row.status = status
    for key, value in fields.items():
        setattr(row, key, value)
    session.flush()
    return row


def best_available_vendor_for_district(
    session: Session, district: str, *, exclude_ids: set[str] | None = None
) -> VendorRow | None:
    """The real matching core behind _eligible_reassignment_candidate()
    below, extracted so it can also back a "suggested vendor" hint on
    the admin review screen — where no VendorJobRow exists yet (the job
    isn't created until approval), just a district/state pulled from the
    site summary.

    Eligible = verified, currently available, and `district` appears in
    the vendor's own self-reported service_area.districts — a vendor
    with no district data at all is never treated as a wildcard match.
    Ties broken by accuracy_score. Returns None (never raises, never
    guesses) when nothing matches."""
    exclude_ids = exclude_ids or set()
    candidates = session.scalars(
        select(VendorRow).where(
            VendorRow.verification_status == "verified",
            VendorRow.availability.is_(True),
        )
    )
    eligible = [
        vendor
        for vendor in candidates
        if str(vendor.id) not in exclude_ids and district in (vendor.service_area.get("districts") or [])
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda v: v.accuracy_score)


def _eligible_reassignment_candidate(session: Session, job: VendorJobRow) -> VendorRow | None:
    """The real "lead passing" decision: which vendor, if any, an
    overdue-and-never-accepted job should move to next.

    Excludes the job's current vendor and every vendor already listed in
    previous_vendor_ids, so a lead can never bounce back to someone who
    already lost it — the job stays overdue and visibly needs an admin's
    manual attention rather than being silently reassigned to someone
    who never said they cover that area."""
    already_tried = {str(v) for v in (job.previous_vendor_ids or [])}
    if job.vendor_id is not None:
        already_tried.add(str(job.vendor_id))
    return best_available_vendor_for_district(session, job.district, exclude_ids=already_tried)


def sweep_vendor_job_sla(
    session: Session, *, at_risk_window: timedelta, reassignment_extension: timedelta
) -> dict[str, int]:
    """The time-bound lead engine — previously `sla_at_risk`/`overdue`
    existed only as status literals nothing ever set (confirmed: no
    scheduled task or code path wrote either one anywhere in this
    codebase before this function). Meant to run periodically from
    workers/tasks_vendors.py::sweep_vendor_sla_task, never from a
    request path — same "never in the request path" discipline VIS-05
    already established for slow/scheduled work.

    Only ever touches jobs still open (queued/accepted/in_progress) —
    submitted/disputed work is finished, not late. Per job:
      - deadline more than `at_risk_window` away: untouched.
      - within `at_risk_window` but not yet passed: marked
        "sla_at_risk" (an early warning; the assigned vendor still owns
        it — no reassignment yet).
      - deadline passed AND still "queued" (never accepted): the real
        lead-passing step — reassigned to the next eligible vendor
        (_eligible_reassignment_candidate) with a fresh deadline
        `reassignment_extension` out and status reset to "queued", so
        the new vendor sees it as a normal live lead, not damaged goods.
      - deadline passed and either already accepted/in_progress, or no
        eligible vendor exists to reassign a queued job to: marked
        "overdue" and left exactly where it is — accepted work in
        progress is never yanked away mid-survey, and a job nobody
        covers is a real gap for an admin to see, not something to hide
        by silently unassigning it.

    Returns counts for the caller (the Celery task) to log — never
    raises on an individual job; one row's edge case must not stop the
    whole sweep."""
    now = datetime.now(UTC)
    at_risk_threshold = now + at_risk_window

    open_jobs = session.scalars(
        select(VendorJobRow).where(VendorJobRow.status.in_(["queued", "accepted", "in_progress"]))
    )

    marked_at_risk = 0
    marked_overdue = 0
    reassigned = 0

    for job in open_jobs:
        if job.deadline > at_risk_threshold:
            continue

        if job.deadline > now:
            if job.status != "sla_at_risk":
                job.status = "sla_at_risk"
                marked_at_risk += 1
                if job.vendor_id is not None:
                    notify_vendor_users(
                        session,
                        job.vendor_id,
                        preference_key="job_deadline_reminders",
                        kind="job_sla_at_risk",
                        title="A job's deadline is approaching",
                        body=f"Job in {job.district}, {job.state} is due {job.deadline.isoformat()}.",
                    )
            continue

        # Deadline has passed. A queued (never-accepted) job is the one
        # case this engine actually passes on to someone else.
        if job.status == "queued":
            next_vendor = _eligible_reassignment_candidate(session, job)
            if next_vendor is not None:
                if job.vendor_id is not None:
                    job.previous_vendor_ids = [*job.previous_vendor_ids, str(job.vendor_id)]
                job.vendor_id = next_vendor.id
                job.status = "queued"
                job.deadline = now + reassignment_extension
                reassigned += 1
                notify_vendor_users(
                    session,
                    next_vendor.id,
                    preference_key="new_job_assignment",
                    kind="job_assigned",
                    title="A new job has been assigned to you",
                    body=f"Job in {job.district}, {job.state}, due {job.deadline.isoformat()}.",
                )
                continue

        if job.status != "overdue":
            job.status = "overdue"
            marked_overdue += 1
            if job.vendor_id is not None:
                notify_vendor_users(
                    session,
                    job.vendor_id,
                    preference_key="job_deadline_reminders",
                    kind="job_overdue",
                    title="A job is now overdue",
                    body=f"Job in {job.district}, {job.state} passed its deadline.",
                )

    session.flush()
    return {"marked_at_risk": marked_at_risk, "marked_overdue": marked_overdue, "reassigned": reassigned}


def decline_job(session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID) -> VendorJobRow | None:
    """A vendor turning down an offered job. Sets status="declined"
    rather than deleting the row (remove_job() below) — an enquiry that
    reached a vendor and got turned down is exactly the kind of state an
    admin must still be able to see and reassign, not lose. Does not
    touch previous_vendor_ids (that list is for auto-reassignment-away-
    from an abandoned job, a different concept from a vendor actively
    declining one they were offered) or vendor_id — the declining
    vendor stays on record as who declined."""
    return update_job_status(session, job_id, vendor_id, status="declined")


def remove_job(session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID) -> bool:
    """The genuine admin cancel/remove primitive — deletes the job row
    entirely. NOT what a vendor declining a job should call (see
    decline_job() above, which preserves history instead); no endpoint
    currently calls this, kept for a future explicit admin
    cancel/remove action."""
    row = get_job(session, job_id, vendor_id)
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def list_submissions(session: Session, vendor_id: str | uuid.UUID) -> list[VendorJobRow]:
    return list_jobs(session, vendor_id, status="submitted")


def dispute_job(
    session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID, *, reason: str
) -> VendorJobRow | None:
    return update_job_status(
        session, job_id, vendor_id, status="submitted", dispute_status="open", dispute_reason=reason
    )


def set_panorama_photo(
    session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID, *, data_url: str
) -> VendorJobRow | None:
    row = get_job(session, job_id, vendor_id)
    if row is None:
        return None
    row.panorama_photo_data_url = data_url
    session.flush()
    return row


def set_shading_notes(
    session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID, *, notes: str
) -> VendorJobRow | None:
    row = get_job(session, job_id, vendor_id)
    if row is None:
        return None
    row.shading_notes = notes
    session.flush()
    return row


def set_obstacle_survey(
    session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID, *, obstacles: list[dict]
) -> VendorJobRow | None:
    """Replaces the whole list — the vendor's capture UI submits its
    current in-memory list on every save, same replace-not-patch
    semantics as update_availability()/set_shading_notes() above."""
    row = get_job(session, job_id, vendor_id)
    if row is None:
        return None
    row.obstacle_survey = obstacles
    session.flush()
    return row


def set_structural_assessment(
    session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID, *, assessment: dict
) -> VendorJobRow | None:
    row = get_job(session, job_id, vendor_id)
    if row is None:
        return None
    row.structural_assessment = assessment
    session.flush()
    return row


def set_electrical_assessment(
    session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID, *, assessment: dict
) -> VendorJobRow | None:
    row = get_job(session, job_id, vendor_id)
    if row is None:
        return None
    row.electrical_assessment = assessment
    session.flush()
    return row


def set_installation_constraints(
    session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID, *, constraints: dict
) -> VendorJobRow | None:
    row = get_job(session, job_id, vendor_id)
    if row is None:
        return None
    row.installation_constraints = constraints
    session.flush()
    return row


def set_safety_assessment(
    session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID, *, assessment: dict
) -> VendorJobRow | None:
    row = get_job(session, job_id, vendor_id)
    if row is None:
        return None
    row.safety_assessment = assessment
    session.flush()
    return row


def set_battery_assessment(
    session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID, *, assessment: dict
) -> VendorJobRow | None:
    row = get_job(session, job_id, vendor_id)
    if row is None:
        return None
    row.battery_assessment = assessment
    session.flush()
    return row


# --------------------------------------------------------------------- #
# payouts
#
# Note: get_earnings_summary() was removed along with the vendor portal's
# Earnings feature. list_payouts() stays — routers/app_admin_vendors.py's
# GET /admin/vendors/{id}/payouts (a separate, admin-facing feature) still
# calls it.
# --------------------------------------------------------------------- #


def list_payouts(session: Session, vendor_id: str | uuid.UUID) -> list[VendorPayoutRow]:
    stmt = (
        select(VendorPayoutRow)
        .where(VendorPayoutRow.vendor_id == uuid.UUID(str(vendor_id)))
        .order_by(VendorPayoutRow.date.desc())
    )
    return list(session.scalars(stmt))
