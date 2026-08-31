"""Owner: karthik (App Platform & Foundation).

Bearer-token login for an individual person — customer, vendor, or admin —
backing the new /app/* web-app surface. Parallel to auth.py, never editing
it: auth.py's current_org() is tenant-scoped API-key auth for server-to-
server integration (API-06); this is session login for a human using the
frontend. The two coexist — nothing here changes how current_org() works.

hash_password()/verify_password() use bcrypt directly rather than passlib
— one hash function doesn't need a whole abstraction layer over it.
create_access_token()/decode_access_token() use pyjwt, HS256, signed with
Settings.jwt_secret — a bearer token, not a DB-backed session, so no
session table and no server-side revocation list exist (yet).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from solarfit.config import get_settings
from solarfit.db import get_session
from solarfit.repositories import users as users_repo

__all__ = [
    "AuthenticatedUser",
    "create_access_token",
    "current_user",
    "decode_access_token",
    "hash_password",
    "require_role",
    "verify_password",
]

_JWT_ALGORITHM = "HS256"


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError (ExpiredSignatureError/InvalidTokenError/...)
    on anything wrong — current_user() below is the one place that turns
    that into an HTTP response, so this function stays a plain decoder
    other callers (e.g. tests) can use directly."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[_JWT_ALGORITHM])


class AuthenticatedUser(BaseModel):
    id: str
    email: str
    role: str
    name: str
    owner_org: str | None = None
    vendor_id: str | None = None


def current_user(
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    """The /app/* equivalent of auth.py's current_org() — resolve the
    calling person, or refuse the request. Every /app/* route except
    /app/auth/login and /app/auth/signup depends on this."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
        row = users_repo.get_by_id(session, payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        # ValueError: a tampered/malformed token's "sub" claim isn't a
        # real UUID — that's just another shape of "invalid token", not
        # a 500. KeyError: a token missing "sub" entirely (shouldn't
        # happen from create_access_token, but never trust the input).
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token") from exc

    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")

    return AuthenticatedUser(
        id=str(row.id),
        email=row.email,
        role=row.role,
        name=row.name,
        owner_org=row.owner_org,
        vendor_id=str(row.vendor_id) if row.vendor_id else None,
    )


def require_role(*roles: str):
    """Dependency factory: `Depends(require_role("admin"))`. 403s when the
    caller's role isn't one of the allowed ones — current_user() itself
    already 401s when there's no valid caller at all."""

    def _check(user: Annotated[AuthenticatedUser, Depends(current_user)]) -> AuthenticatedUser:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role: {', '.join(roles)}")
        return user

    return _check
