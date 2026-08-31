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
