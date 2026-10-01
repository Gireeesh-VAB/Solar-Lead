from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from solarfit.auth import check_rate_limit
from solarfit.auth_users import (
    AuthenticatedUser,
    create_access_token,
    current_user,
    hash_password,
    verify_password,
)
from solarfit.db import get_session, session_scope
from solarfit.repositories import audit as audit_repo
from solarfit.repositories import users as users_repo
from solarfit.repositories.users import UserRow
from solarfit.routers.common import actor_audit_fields, request_audit_meta

router = APIRouter(prefix="/app/auth", tags=["app-auth"])

MIN_PASSWORD_LENGTH = 8

# Deliberately simple — a permissive shape check, not full RFC 5322
# validation. pydantic's EmailStr needs the email-validator package,
# which isn't a dependency of this project; a bad address still just
# fails to receive anything, so a shape check is enough at this boundary.
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

# Login attempts are keyed by the email being attempted, not a stable
# caller identity (there isn't one before login succeeds) — same
# fixed-window counter auth.py's API-key path already uses, reused as-is
# rather than reinventing rate limiting for this second auth surface.
LOGIN_RATE_LIMIT_PER_MINUTE = 10


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SignupRequest(_CamelModel):
    email: str = Field(pattern=_EMAIL_PATTERN, max_length=255)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    name: str = Field(min_length=1, max_length=255)
    owner_org: str = Field(min_length=1, max_length=255)


class LoginRequest(_CamelModel):
    email: str = Field(pattern=_EMAIL_PATTERN, max_length=255)
    password: str


class ChangePasswordRequest(_CamelModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class UserOut(_CamelModel):
    id: str
    email: str
    role: str
    name: str
    owner_org: str | None
    vendor_id: str | None
    tier: str | None
    status: str | None
    billing_contact_email: str | None
    created_at: datetime


class AuthResponse(_CamelModel):
    token: str
    user: UserOut


def _user_out(row: UserRow) -> UserOut:
    return UserOut(
        id=str(row.id),
        email=row.email,
        role=row.role,
        name=row.name,
        owner_org=row.owner_org,
        vendor_id=str(row.vendor_id) if row.vendor_id else None,
        tier=row.tier,
        status=row.status,
        billing_contact_email=row.billing_contact_email,
        created_at=row.created_at,
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(
    payload: SignupRequest, session: Annotated[Session, Depends(get_session)]
) -> AuthResponse:
    """Self-service — customer role only, hardcoded here regardless of
    anything a client might send. Admin and vendor accounts are
    provisioned elsewhere, not through this endpoint.

    owner_org is a free-text company/account name: signing up with one
    that already exists joins it as an additional seat (see
    repositories/users.py::list_by_owner_org) rather than erroring —
    there's no separate "create an org" step to fail against.
    """
    try:
        row = users_repo.create_user(
            session,
            email=payload.email,
            password_hash=hash_password(payload.password),
            name=payload.name,
            role="customer",
            owner_org=payload.owner_org,
        )
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "an account with this email already exists") from exc

    # Explicit commit here, not left to get_session()'s post-yield teardown:
    # FastAPI runs yield-dependency cleanup for sync (threadpool) routes
    # after the response has already been sent to the client, so a fast
    # client (e.g. a browser firing an immediate follow-up call with the
    # new bearer token) can lose the race against the commit and see
    # "invalid or expired token" on a brand-new, correctly-issued token —
    # reproduced via a Playwright-driven signup immediately followed by a
    # PATCH /app/customer/profile call. Committing before we return closes
    # that window for the one flow guaranteed to have an immediate
    # follow-up request (signup -> profile update -> home).
    session.commit()

    token = create_access_token(str(row.id), row.role)
    return AuthResponse(token=token, user=_user_out(row))


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest, request: Request, session: Annotated[Session, Depends(get_session)]
) -> AuthResponse:
    allowed, _remaining = check_rate_limit(f"login:{payload.email}", LOGIN_RATE_LIMIT_PER_MINUTE)
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"rate limit of {LOGIN_RATE_LIMIT_PER_MINUTE}/min exceeded",
            headers={"Retry-After": "60"},
        )

    row = users_repo.get_by_email(session, payload.email)
    # Same message whether the email is unknown or the password is wrong —
    # distinguishing them tells an attacker which of their guesses is a
    # real account, the same anti-enumeration reasoning auth.py already
    # applies to unknown-vs-revoked API keys.
    if row is None or not verify_password(payload.password, row.password_hash):
        # Own transaction, committed before raising: get_session()'s
        # teardown rolls back on any exception out of this function (see
        # db.py::session_scope), which would otherwise silently discard
        # the very audit row a failed-login attempt exists to record.
        with session_scope() as audit_session:
            audit_repo.write_audit_log(
                audit_session,
                actor=payload.email,
                action="auth.login_failed",
                target=payload.email,
                details=f"failed login attempt for {payload.email}",
                actor_id=str(row.id) if row is not None else None,
                actor_type=row.role if row is not None else None,
                actor_role=row.role if row is not None else None,
                entity_type="user",
                entity_id=str(row.id) if row is not None else payload.email,
                **request_audit_meta(request),
            )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")

    users_repo.touch_last_login(session, row.id)
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(AuthenticatedUser(id=str(row.id), email=row.email, role=row.role, name=row.name)),
        action="auth.login",
        target=str(row.id),
        details=f"{row.email} logged in",
        entity_type="user",
        entity_id=str(row.id),
        **request_audit_meta(request),
    )
    token = create_access_token(str(row.id), row.role)
    return AuthResponse(token=token, user=_user_out(row))


@router.get("/me", response_model=UserOut)
def me(
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> UserOut:
    row = users_repo.get_by_id(session, user.id)
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    return _user_out(row)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Role-agnostic — any authenticated user (vendor Settings page is
    the first caller, but nothing here is vendor-specific).

    Note this does NOT invalidate the bearer token already in the
    caller's browser: auth is fully stateless (no session/revocation
    store — see auth_users.py's module docstring), so an old token stays
    valid until it naturally expires regardless of a password change.
    That's an existing property of the whole auth system, not something
    this endpoint could fix on its own.
    """
    row = users_repo.get_by_id(session, user.id)
    if row is None or not verify_password(payload.current_password, row.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "current password is incorrect")
    users_repo.update_password(session, user.id, password_hash=hash_password(payload.new_password))
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(user),
        action="auth.password_changed",
        target=user.id,
        details=f"{user.email} changed their password",
        entity_type="user",
        entity_id=user.id,
        **request_audit_meta(request),
    )
