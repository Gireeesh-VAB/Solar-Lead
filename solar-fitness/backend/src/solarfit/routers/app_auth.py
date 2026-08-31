"""Owner: karthik (App Platform & Foundation).

The first /app/* router — establishes the camelCase-response convention
every later /app/* endpoint (omkar's, keerthana's) follows: response
models use Pydantic's to_camel alias generator so JSON keys match
lib/types.ts field-for-field (ownerOrg, not owner_org), rather than each
router hand-renaming fields one at a time.

POST /app/auth/signup and POST /app/auth/login are the only two /app/*
routes that don't require current_user() — everything else does.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
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
from solarfit.db import get_session
from solarfit.repositories import users as users_repo
from solarfit.repositories.users import UserRow

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

    token = create_access_token(str(row.id), row.role)
    return AuthResponse(token=token, user=_user_out(row))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, session: Annotated[Session, Depends(get_session)]) -> AuthResponse:
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
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")

    users_repo.touch_last_login(session, row.id)
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
