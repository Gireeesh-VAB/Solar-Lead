"""Owner: karthik (App Platform & Foundation).

Individual login identity for all three portal roles — customer, vendor,
admin — backing the new /app/* web-app auth surface (auth_users.py).
Separate from auth.py's ApiKeyRow: that's tenant-scoped, server-to-server
API-key auth (API-06); this is bearer-token login for a person.

owner_org is the one field that actually connects a customer's login to
the sites/API-key tenant system that already exists — it's the same
plain string sites.owner_org / api_keys.owner_org already use, not a new
identity space. Multiple users can share one (signing up with the same
company name joins as an additional seat), which is what makes
list_by_owner_org() below meaningful for the frontend's Tenant.users[].

vendor_id has no FK yet — keerthana's vendors table doesn't exist when
this migration lands. Add the FK in a follow-up migration once it does,
the same pattern already used for site_id on calibration_records/
ml_training_samples before repositories/sites.py existed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, String, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base

__all__ = [
    "UserRow",
    "create_user",
    "get_by_email",
    "get_by_id",
    "list_by_owner_org",
    "list_by_role",
    "list_by_vendor_id",
    "set_status",
    "touch_last_login",
    "update_password",
    "update_profile",
]


class UserRow(Base):
    """Individual login — see module docstring for the role/owner_org shape."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # admin | customer | vendor
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    owner_org: Mapped[str | None] = mapped_column(String(255), nullable=True)  # customer only
    tier: Mapped[str | None] = mapped_column(String(32), nullable=True)  # customer only
    status: Mapped[str | None] = mapped_column(String(16), nullable=True, default="active")
    billing_contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    vendor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Consumer "checks" self-service profile (lib/fixtures/customer.ts's
    # CustomerProfile) — additive, no other role uses these.
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notify_on_complete: Mapped[bool] = mapped_column(nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def create_user(
    session: Session,
    *,
    email: str,
    password_hash: str,
    name: str,
    role: str = "customer",
    owner_org: str | None = None,
    **extra: Any,
) -> UserRow:
    """Raises sqlalchemy.exc.IntegrityError on a duplicate email — the
    router's job to catch and turn into a 409, not this function's."""
    row = UserRow(
        email=email,
        password_hash=password_hash,
        name=name,
        role=role,
        owner_org=owner_org,
        **extra,
    )
    session.add(row)
    session.flush()
    return row


def get_by_email(session: Session, email: str) -> UserRow | None:
    return session.scalars(select(UserRow).where(UserRow.email == email)).one_or_none()


def get_by_id(session: Session, user_id: str | uuid.UUID) -> UserRow | None:
    return session.get(UserRow, uuid.UUID(str(user_id)))


def list_by_owner_org(session: Session, owner_org: str) -> list[UserRow]:
    """Backs the frontend's Tenant.users[] — every login sharing one
    customer account. Nothing calls this yet (keerthana's customer-account
    admin work does); built now since it's a one-line query and the
    natural companion to owner_org existing on the row at all."""
    stmt = select(UserRow).where(UserRow.owner_org == owner_org).order_by(UserRow.created_at)
    return list(session.scalars(stmt))


def list_by_vendor_id(session: Session, vendor_id: str | uuid.UUID) -> list[UserRow]:
    """Every login belonging to one vendor — the vendor-sub-users
    equivalent of list_by_owner_org() above. Backs
    routers/app_admin_vendors.py's GET /{vendor_id}/users."""
    stmt = (
        select(UserRow)
        .where(UserRow.vendor_id == uuid.UUID(str(vendor_id)))
        .order_by(UserRow.created_at)
    )
    return list(session.scalars(stmt))


def list_by_role(session: Session, role: str) -> list[UserRow]:
    """Every login with one role — backs "notify all admins" (there is
    no per-admin notification-preference concept, unlike vendors'
    notification_preferences)."""
    stmt = select(UserRow).where(UserRow.role == role).order_by(UserRow.created_at)
    return list(session.scalars(stmt))


def touch_last_login(session: Session, user_id: str | uuid.UUID) -> None:
    row = session.get(UserRow, uuid.UUID(str(user_id)))
    if row is not None:
        row.last_login_at = datetime.now(UTC)
        session.flush()


def update_profile(
    session: Session,
    user_id: str | uuid.UUID,
    *,
    name: str | None = None,
    phone: str | None = None,
    notify_on_complete: bool | None = None,
) -> UserRow | None:
    """Consumer "checks" self-service profile update. Deliberately no
    email field here — email is also the login identity (unique,
    case-sensitive-as-stored) and a live email-change flow (collision
    check, re-verification) is out of this pass's scope; a payload that
    includes one is silently ignored at the router layer, not accepted
    and not erroring."""
    row = get_by_id(session, user_id)
    if row is None:
        return None
    if name is not None:
        row.name = name
    if phone is not None:
        row.phone = phone
    if notify_on_complete is not None:
        row.notify_on_complete = notify_on_complete
    session.flush()
    return row


def set_status(session: Session, user_id: str | uuid.UUID, *, status: str) -> UserRow | None:
    """Activate/deactivate a login — the vendor-sub-user equivalent of
    vendors_repo.set_verification_status(). Same single-field-write shape
    as update_password() below; the router's job to audit-log it."""
    row = get_by_id(session, user_id)
    if row is None:
        return None
    row.status = status
    session.flush()
    return row


def update_password(session: Session, user_id: str | uuid.UUID, *, password_hash: str) -> UserRow | None:
    """Settings page's "Change password". Caller (routers/app_auth.py)
    has already verified the current password before calling this —
    this function just writes the new hash, same single-field-update
    shape as update_profile() above."""
    row = get_by_id(session, user_id)
    if row is None:
        return None
    row.password_hash = password_hash
    session.flush()
    return row
