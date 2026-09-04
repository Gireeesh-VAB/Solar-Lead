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
app_checks.py::complete_check() queues an unassigned job when a check
resolves to SUITABLE_SUBJECT_TO_SURVEY, since that verdict means the
engine couldn't be confident from imagery alone and a vendor needs to
confirm the roof in person. Every other write in this module still
takes an existing job/vendor id — this is the only one that creates a
vendor_jobs row from scratch. Tests otherwise seed rows directly
against these ORM classes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base

__all__ = [
    "VendorAccuracyHistoryRow",
    "VendorJobRow",
    "VendorPayoutRow",
    "VendorRow",
    "count_active_jobs_for_sites",
    "create_job",
    "create_vendor",
    "dispute_job",
    "get_accuracy_history",
    "get_earnings_summary",
    "get_job",
    "get_vendor",
    "list_jobs",
    "list_payouts",
    "list_submissions",
    "list_vendors",
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
    "update_availability",
    "update_job_status",
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
        VendorJobRow.site_id.in_(site_uuids), VendorJobRow.status != "submitted"
    )
    return len(list(session.scalars(stmt)))


def vendor_admin_stats(session: Session, vendor_id: str | uuid.UUID) -> dict[str, Any]:
    """activeJobs/totalJobsCompleted/slaCompliancePct — computed at read
    time from vendor_jobs, never stored, so they can't drift from the
    real job history. "Completed" = submitted; "active" = everything
    else (queued/accepted/in_progress/sla_at_risk/overdue); SLA
    compliance = the fraction of submitted jobs turned in at or before
    their deadline — an honest 0.0 (not a fabricated number) when
    nothing has been submitted yet."""
    vid = uuid.UUID(str(vendor_id))
    rows = list(session.scalars(select(VendorJobRow).where(VendorJobRow.vendor_id == vid)))

    submitted = [r for r in rows if r.status == "submitted"]
    active = [r for r in rows if r.status != "submitted"]
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


def get_accuracy_history(session: Session, vendor_id: str | uuid.UUID) -> list[VendorAccuracyHistoryRow]:
    stmt = (
        select(VendorAccuracyHistoryRow)
        .where(VendorAccuracyHistoryRow.vendor_id == uuid.UUID(str(vendor_id)))
        .order_by(VendorAccuracyHistoryRow.recorded_at)
    )
    return list(session.scalars(stmt))


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


def get_job(session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID) -> VendorJobRow | None:
    """Scoped to vendor_id — a job assigned to someone else is treated as
    not found, the same not-403 reasoning routers/sites.py's
    _owned_or_404 already uses (a 403 would confirm the id exists)."""
    row = session.get(VendorJobRow, uuid.UUID(str(job_id)))
    if row is None or row.vendor_id != uuid.UUID(str(vendor_id)):
        return None
    return row


def update_job_status(
    session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID, *, status: str, **fields: Any
) -> VendorJobRow | None:
    row = get_job(session, job_id, vendor_id)
    if row is None:
        return None
    row.status = status
    for key, value in fields.items():
        setattr(row, key, value)
    session.flush()
    return row


def remove_job(session: Session, job_id: str | uuid.UUID, vendor_id: str | uuid.UUID) -> bool:
    """declineVendorJob's real semantics per lib/api/client.ts: the job is
    removed from the vendor's queue entirely, not left behind with a
    'declined' status."""
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
# payouts / earnings
# --------------------------------------------------------------------- #


def list_payouts(session: Session, vendor_id: str | uuid.UUID) -> list[VendorPayoutRow]:
    stmt = (
        select(VendorPayoutRow)
        .where(VendorPayoutRow.vendor_id == uuid.UUID(str(vendor_id)))
        .order_by(VendorPayoutRow.date.desc())
    )
    return list(session.scalars(stmt))


def get_earnings_summary(session: Session, vendor_id: str | uuid.UUID) -> dict[str, Any]:
    """weekTotalInr/jobsCompletedThisWeek are computed from vendor_jobs
    submitted in the last 7 days; pending/paid/disputed are computed from
    vendor_payouts by status — two different tables because a submitted
    job and its eventual payout are recorded independently, the same way
    the frontend's mock data keeps them (client.ts's getVendorEarningsSummary
    derives weekly figures from jobs, and pending/paid/disputed from
    payouts)."""
    vid = uuid.UUID(str(vendor_id))
    week_ago = datetime.now(UTC) - timedelta(days=7)

    jobs_this_week = list(
        session.scalars(
            select(VendorJobRow).where(
                VendorJobRow.vendor_id == vid,
                VendorJobRow.status == "submitted",
                VendorJobRow.submitted_at >= week_ago,
            )
        )
    )
    week_total = sum(float(j.reconciled_payout_inr or j.payout_inr) for j in jobs_this_week)

    payouts = list_payouts(session, vendor_id)
    pending = sum(float(p.amount) for p in payouts if p.status == "pending")
    paid = sum(float(p.amount) for p in payouts if p.status == "paid")
    disputed = sum(float(p.amount) for p in payouts if p.status == "disputed")

    return {
        "week_total_inr": week_total,
        "pending_inr": pending,
        "paid_inr": paid,
        "disputed_inr": disputed,
        "jobs_completed_this_week": len(jobs_this_week),
    }
