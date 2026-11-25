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

import secrets
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, hash_password, require_permission
from solarfit.db import get_session
from solarfit.repositories import audit as audit_repo
from solarfit.repositories import users as users_repo
from solarfit.repositories import vendor_reviews as vendor_reviews_repo
from solarfit.repositories import vendors as repo
from solarfit.repositories.vendors import VendorRow
from solarfit.routers.app_vendor import PayoutEntryOut, VendorJobOut, _job_out, _payout_out
from solarfit.routers.common import CamelModel, IndianMobile, actor_audit_fields

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
    average_rating: float | None = None
    review_count: int = 0
    service_area: str
    joined_at: datetime
    payout_method: Literal["UPI", "Bank transfer"]
    legal_name: str | None = None
    gst_number: str | None = None
    pan_number: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    certifications: list[str] = Field(default_factory=list)


class VendorCreateRequest(CamelModel):
    # max_length on every optional field below matches its VendorRow
    # column exactly (repositories/vendors.py) — Postgres raises
    # StringDataRightTruncation, an unhandled 500, on an oversized
    # varchar insert rather than silently truncating; catching it here
    # instead turns it into an ordinary 422 the admin can actually act on.
    name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    gst_number: str | None = Field(default=None, max_length=32)
    pan_number: str | None = Field(default=None, max_length=16)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_phone: IndianMobile = None
    contact_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=128)
    state: str | None = Field(default=None, max_length=128)
    pincode: str | None = Field(default=None, max_length=16)
    service_area_region: str = Field(min_length=1, max_length=255)
    service_area_districts: list[str] = Field(default_factory=list)
    payout_method_type: Literal["UPI", "Bank transfer"]
    payout_masked_account: str = Field(min_length=1, max_length=64)
    certifications: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)


class VendorCreateResponse(CamelModel):
    vendor: AdminVendorSummaryOut
    login_email: str
    temporary_password: str


class VendorUserOut(CamelModel):
    id: str
    email: str
    name: str
    status: Literal["active", "inactive"]
    created_at: datetime
    last_login_at: datetime | None = None


class VendorUserCreateRequest(CamelModel):
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)


class VendorUserCreateResponse(CamelModel):
    user: VendorUserOut
    login_email: str
    temporary_password: str


class VendorUserStatusRequest(CamelModel):
    status: Literal["active", "inactive"]


def _vendor_user_out(row: users_repo.UserRow) -> VendorUserOut:
    return VendorUserOut(
        id=str(row.id),
        email=row.email,
        name=row.name,
        status=row.status or "active",
        created_at=row.created_at,
        last_login_at=row.last_login_at,
    )


def _summary_out(session: Session, row: VendorRow) -> AdminVendorSummaryOut:
    stats = repo.vendor_admin_stats(session, row.id)
    rating = vendor_reviews_repo.vendor_rating_summary(session, row.id)
    return AdminVendorSummaryOut(
        id=str(row.id),
        name=row.name,
        verification_status=row.verification_status,
        accuracy_score=row.accuracy_score,
        sla_compliance_pct=stats["sla_compliance_pct"],
        active_jobs=stats["active_jobs"],
        total_jobs_completed=stats["total_jobs_completed"],
        average_rating=rating["average_rating"],
        review_count=rating["review_count"],
        service_area=str(row.service_area.get("region", "")),
        joined_at=row.joined_at,
        payout_method=row.payout_method_type,
        legal_name=row.legal_name,
        gst_number=row.gst_number,
        pan_number=row.pan_number,
        contact_name=row.contact_name,
        contact_phone=row.contact_phone,
        contact_email=row.contact_email,
        address_line1=row.address_line1,
        address_line2=row.address_line2,
        city=row.city,
        state=row.state,
        pincode=row.pincode,
        certifications=list(row.certifications or []),
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
    existing = _vendor_or_404(session, vendor_id)
    previous_status = existing.verification_status
    row = repo.set_verification_status(session, vendor_id, status_value)
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(admin),
        action=action,
        target=str(row.id),
        details=f"{admin.email} set vendor {row.id} ({row.name}) verification_status to {status_value}",
        entity_type="vendor",
        vendor_id=str(row.id),
        previous_value={"verificationStatus": previous_status},
        new_value={"verificationStatus": status_value},
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
    _admin: Annotated[AuthenticatedUser, Depends(require_permission("VENDOR_VIEW"))],
    q: Annotated[str | None, Query()] = None,
    verification_status: Annotated[str | None, Query(alias="verificationStatus")] = None,
    sort: Annotated[Literal["accuracy", "sla"] | None, Query()] = None,
) -> list[AdminVendorSummaryOut]:
    rows = repo.list_vendors(session, q=q, verification_status=verification_status, sort=sort)
    return [_summary_out(session, r) for r in rows]


@router.get("/verification-queue", response_model=list[AdminVendorSummaryOut])
def verification_queue(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AuthenticatedUser, Depends(require_permission("VENDOR_VIEW"))],
) -> list[AdminVendorSummaryOut]:
    rows = repo.list_vendors(session, verification_status="pending")
    return [_summary_out(session, r) for r in rows]


@router.post("", response_model=VendorCreateResponse, status_code=status.HTTP_201_CREATED)
def create_vendor(
    payload: VendorCreateRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_permission("VENDOR_CREATE"))],
) -> VendorCreateResponse:
    """Admin "Add Vendor" flow: creates both the vendor profile row and
    a linked login (users.role="vendor", users.vendor_id set) in one
    request, since there's no separate invite/claim flow yet. There's
    no email infrastructure in this codebase to send the new login
    anywhere, so a one-time temporary password is generated and
    returned directly in the response for the admin to hand off."""
    if users_repo.get_by_email(session, payload.contact_email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "an account with this email already exists")

    vendor_row = repo.create_vendor(
        session,
        name=payload.name,
        legal_name=payload.legal_name,
        gst_number=payload.gst_number,
        pan_number=payload.pan_number,
        contact_name=payload.contact_name,
        contact_phone=payload.contact_phone,
        contact_email=payload.contact_email,
        address_line1=payload.address_line1,
        address_line2=payload.address_line2,
        city=payload.city,
        state=payload.state,
        pincode=payload.pincode,
        service_area={"region": payload.service_area_region, "districts": payload.service_area_districts},
        payout_method_type=payload.payout_method_type,
        payout_masked_account=payload.payout_masked_account,
        certifications=payload.certifications,
        documents=payload.documents,
    )

    temporary_password = secrets.token_urlsafe(9)
    try:
        users_repo.create_user(
            session,
            email=payload.contact_email,
            password_hash=hash_password(temporary_password),
            name=payload.contact_name or payload.name,
            role="vendor",
            vendor_id=vendor_row.id,
        )
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "an account with this email already exists") from exc

    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(admin),
        action="vendor.created",
        target=str(vendor_row.id),
        details=f"{admin.email} created vendor {vendor_row.name} with login {payload.contact_email}",
        entity_type="vendor",
        vendor_id=str(vendor_row.id),
        new_value={"name": vendor_row.name, "contactEmail": payload.contact_email},
    )

    return VendorCreateResponse(
        vendor=_summary_out(session, vendor_row),
        login_email=payload.contact_email,
        temporary_password=temporary_password,
    )


@router.get("/{vendor_id}", response_model=AdminVendorSummaryOut)
def get_vendor(
    vendor_id: str,
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AuthenticatedUser, Depends(require_permission("VENDOR_VIEW"))],
) -> AdminVendorSummaryOut:
    row = _vendor_or_404(session, vendor_id)
    return _summary_out(session, row)


@router.get("/{vendor_id}/jobs", response_model=list[VendorJobOut])
def get_vendor_jobs(
    vendor_id: str,
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AuthenticatedUser, Depends(require_permission("VENDOR_VIEW"))],
) -> list[VendorJobOut]:
    """Admin-scoped equivalent of app_vendor.py's GET /jobs — takes
    vendor_id from the path instead of the caller's own session, so an
    admin can inspect any vendor's job history (was previously
    mis-wired on the frontend to the logged-in admin's own, nonexistent
    vendor scope)."""
    _vendor_or_404(session, vendor_id)
    rows = repo.list_jobs(session, vendor_id)
    return [_job_out(session, r) for r in rows]


@router.get("/{vendor_id}/payouts", response_model=list[PayoutEntryOut])
def get_vendor_payouts(
    vendor_id: str,
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AuthenticatedUser, Depends(require_permission("VENDOR_VIEW"))],
) -> list[PayoutEntryOut]:
    _vendor_or_404(session, vendor_id)
    return [_payout_out(r) for r in repo.list_payouts(session, vendor_id)]


@router.get("/{vendor_id}/users", response_model=list[VendorUserOut])
def list_vendor_users(
    vendor_id: str,
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AuthenticatedUser, Depends(require_permission("VENDOR_VIEW"))],
) -> list[VendorUserOut]:
    _vendor_or_404(session, vendor_id)
    return [_vendor_user_out(r) for r in users_repo.list_by_vendor_id(session, vendor_id)]


@router.post(
    "/{vendor_id}/users", response_model=VendorUserCreateResponse, status_code=status.HTTP_201_CREATED
)
def create_vendor_user(
    vendor_id: str,
    payload: VendorUserCreateRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_permission("VENDOR_EDIT"))],
) -> VendorUserCreateResponse:
    """A second (or third, ...) login for a vendor already on the
    platform — e.g. a surveyor or installer seat alongside the vendor's
    main account. Same "admin creates it, no self-signup, one-time
    temporary password returned directly" shape as create_vendor()
    above, since there's still no email infrastructure to send it
    anywhere else."""
    vendor_row = _vendor_or_404(session, vendor_id)
    if users_repo.get_by_email(session, payload.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "an account with this email already exists")

    temporary_password = secrets.token_urlsafe(9)
    try:
        user_row = users_repo.create_user(
            session,
            email=payload.email,
            password_hash=hash_password(temporary_password),
            name=payload.name,
            role="vendor",
            vendor_id=vendor_row.id,
        )
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "an account with this email already exists") from exc

    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(admin),
        action="vendor.user_created",
        target=str(user_row.id),
        details=f"{admin.email} created user {payload.email} for vendor {vendor_row.name} ({vendor_row.id})",
        entity_type="vendor_user",
        vendor_id=str(vendor_row.id),
        new_value={"email": payload.email, "name": payload.name},
    )

    return VendorUserCreateResponse(
        user=_vendor_user_out(user_row),
        login_email=payload.email,
        temporary_password=temporary_password,
    )


@router.patch("/{vendor_id}/users/{user_id}/status", response_model=VendorUserOut)
def set_vendor_user_status(
    vendor_id: str,
    user_id: str,
    payload: VendorUserStatusRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_permission("VENDOR_EDIT"))],
) -> VendorUserOut:
    """Activate/deactivate one of this vendor's sub-user logins —
    doesn't touch the vendor's own verification_status (set_status()
    above), a separate concern from suspending the vendor as a whole."""
    _vendor_or_404(session, vendor_id)
    user_row = users_repo.get_by_id(session, user_id)
    if user_row is None or str(user_row.vendor_id) != str(vendor_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor user not found")

    previous_status = user_row.status
    updated = users_repo.set_status(session, user_id, status=payload.status)
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(admin),
        action="vendor.user_status_set",
        target=str(user_id),
        details=f"{admin.email} set user {user_row.email} status to {payload.status}",
        entity_type="vendor_user",
        vendor_id=str(vendor_id),
        previous_value={"status": previous_status},
        new_value={"status": payload.status},
    )
    return _vendor_user_out(updated)


@router.post("/{vendor_id}/suspend", response_model=AdminVendorSummaryOut)
def suspend_vendor(
    vendor_id: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_permission("VENDOR_SUSPEND"))],
) -> AdminVendorSummaryOut:
    return _set_status(session, admin, vendor_id, "suspended", "vendor.suspend")


@router.post("/{vendor_id}/reinstate", response_model=AdminVendorSummaryOut)
def reinstate_vendor(
    vendor_id: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_permission("VENDOR_SUSPEND"))],
) -> AdminVendorSummaryOut:
    return _set_status(session, admin, vendor_id, "verified", "vendor.reinstate")


@router.post("/{vendor_id}/verification/approve", response_model=AdminVendorSummaryOut)
def approve_verification(
    vendor_id: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_permission("VENDOR_APPROVE"))],
) -> AdminVendorSummaryOut:
    return _set_status(session, admin, vendor_id, "verified", "vendor.verification_approve")


@router.post("/{vendor_id}/verification/reject", response_model=AdminVendorSummaryOut)
def reject_verification(
    vendor_id: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_permission("VENDOR_APPROVE"))],
) -> AdminVendorSummaryOut:
    result = _set_status(session, admin, vendor_id, "rejected", "vendor.verification_reject")
    repo.notify_vendor_users(
        session,
        vendor_id,
        preference_key="submission_and_payout_updates",
        kind="vendor_verification_rejected",
        title="Your vendor verification was rejected",
    )
    return result
