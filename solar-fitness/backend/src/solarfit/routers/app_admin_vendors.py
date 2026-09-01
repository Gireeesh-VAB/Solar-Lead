"""Owner: karthik (App Platform & Foundation).

Admin oversight of vendors — closes a real gap found during a
frontend/backend sync audit: the frontend's listAdminVendors/
getAdminVendor/suspendVendor/reinstateVendor/listVendorVerificationQueue/
approveVendorVerification/rejectVendorVerification (7 functions) had no
backend router at all, despite keerthana's repositories/vendors.py
already carrying the vendor tables these need to read/write.

Its own router file, deliberately not folded into app_admin_platform.py/
app_admin_engine.py/app_admin_customers.py/app_calibration_ml.py — same
one-router-per-admin-area convention every other /app/admin/* file
already follows to avoid merge collisions.

Every mutation here writes an audit-log entry, matching every other
admin router's convention (app_admin_platform.py, app_calibration_ml.py).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, require_role
from solarfit.db import get_session
from solarfit.repositories import audit as audit_repo
from solarfit.repositories import vendors as repo
from solarfit.repositories.vendors import VendorRow
from solarfit.routers.common import CamelModel

router = APIRouter(prefix="/app/admin/vendors", tags=["app-admin-vendors"])


# --------------------------------------------------------------------- #
# schemas
# --------------------------------------------------------------------- #


class AdminVendorSummaryOut(CamelModel):
    id: str
    name: str
    verification_status: Literal["verified", "pending", "rejected", "suspended"]
    accuracy_score: float
    sla_compliance_pct: float
    active_jobs: int
    total_jobs_completed: int
    service_area: str
    joined_at: datetime
    payout_method: Literal["UPI", "Bank transfer"]


def _summary_out(session: Session, row: VendorRow) -> AdminVendorSummaryOut:
    stats = repo.vendor_admin_stats(session, row.id)
    return AdminVendorSummaryOut(
        id=str(row.id),
        name=row.name,
        verification_status=row.verification_status,
        accuracy_score=row.accuracy_score,
        sla_compliance_pct=stats["sla_compliance_pct"],
        active_jobs=stats["active_jobs"],
        total_jobs_completed=stats["total_jobs_completed"],
        service_area=str(row.service_area.get("region", "")),
        joined_at=row.joined_at,
        payout_method=row.payout_method_type,
    )


def _vendor_or_404(session: Session, vendor_id: str) -> VendorRow:
    try:
        row = repo.get_vendor(session, vendor_id)
    except ValueError as exc:  # malformed UUID
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found") from exc
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    return row


def _set_status(
    session: Session, admin: AuthenticatedUser, vendor_id: str, status_value: str, action: str
) -> AdminVendorSummaryOut:
    _vendor_or_404(session, vendor_id)
    row = repo.set_verification_status(session, vendor_id, status_value)
    audit_repo.write_audit_log(
        session,
        actor=admin.email,
        action=action,
        target=str(row.id),
        details=f"{admin.email} set vendor {row.id} ({row.name}) verification_status to {status_value}",
    )
    return _summary_out(session, row)


# --------------------------------------------------------------------- #
# endpoints
# --------------------------------------------------------------------- #

# GET /verification-queue is registered BEFORE GET /{vendor_id} — FastAPI
# matches routes in registration order, and "/{vendor_id}" would
# otherwise capture "verification-queue" as a path parameter first,
# same reasoning app_sites.py's portfolio-summary route documents.


@router.get("", response_model=list[AdminVendorSummaryOut])
def list_vendors(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
    q: Annotated[str | None, Query()] = None,
    verification_status: Annotated[str | None, Query(alias="verificationStatus")] = None,
    sort: Annotated[Literal["accuracy", "sla"] | None, Query()] = None,
) -> list[AdminVendorSummaryOut]:
    rows = repo.list_vendors(session, q=q, verification_status=verification_status, sort=sort)
    return [_summary_out(session, r) for r in rows]


@router.get("/verification-queue", response_model=list[AdminVendorSummaryOut])
def verification_queue(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> list[AdminVendorSummaryOut]:
    rows = repo.list_vendors(session, verification_status="pending")
    return [_summary_out(session, r) for r in rows]


@router.get("/{vendor_id}", response_model=AdminVendorSummaryOut)
def get_vendor(
    vendor_id: str,
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> AdminVendorSummaryOut:
    row = _vendor_or_404(session, vendor_id)
    return _summary_out(session, row)


@router.post("/{vendor_id}/suspend", response_model=AdminVendorSummaryOut)
def suspend_vendor(
    vendor_id: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> AdminVendorSummaryOut:
    return _set_status(session, admin, vendor_id, "suspended", "vendor.suspend")


@router.post("/{vendor_id}/reinstate", response_model=AdminVendorSummaryOut)
def reinstate_vendor(
    vendor_id: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> AdminVendorSummaryOut:
    return _set_status(session, admin, vendor_id, "verified", "vendor.reinstate")


@router.post("/{vendor_id}/verification/approve", response_model=AdminVendorSummaryOut)
def approve_verification(
    vendor_id: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> AdminVendorSummaryOut:
    return _set_status(session, admin, vendor_id, "verified", "vendor.verification_approve")


@router.post("/{vendor_id}/verification/reject", response_model=AdminVendorSummaryOut)
def reject_verification(
    vendor_id: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> AdminVendorSummaryOut:
    return _set_status(session, admin, vendor_id, "rejected", "vendor.verification_reject")
