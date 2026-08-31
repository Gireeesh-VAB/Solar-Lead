"""Owner: Person 1 (Site & Geometry).

API-06 — API-key auth dependency + per-tenant rate limiting.

Replaces the `X-Owner-Org` placeholder that routers/sites.py shipped
with. Keys arrive in an `X-API-Key` header and resolve to the owning
tenant; every downstream ownership filter then keys off a value the
caller cannot choose for themselves.

Storage
-------
Only a SHA-256 hash of the key is stored, never the key itself. A dump
of the `api_keys` table therefore grants nothing — the same reason
password hashes exist. Keys are shown to the operator exactly once, at
creation.

A short random `prefix` is stored in clear so a key can be identified in
a UI ("sk_live_a1b2…") and revoked without the operator having to paste
the secret back in.

Rate limiting
-------------
A fixed-window counter per key per minute, in Redis. Fixed-window is
deliberately the simple choice: it can allow up to 2x the limit across a
window boundary, which is fine for protecting a backend from a runaway
import script. It is NOT a billing meter, and should not be used as one.

If Redis is unreachable the request is ALLOWED rather than blocked —
a rate limiter that hard-fails an entire API when its cache dies has
turned a nice-to-have into a single point of failure.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

import redis
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import DateTime, Integer, String, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.config import get_settings
from solarfit.db import Base, get_session

__all__ = [
    "DEFAULT_RATE_LIMIT_PER_MINUTE",
    "PREFIX_LENGTH",
    "ApiKeyRow",
    "create_api_key",
    "current_org",
    "hash_key",
    "resolve_api_key",
]

DEFAULT_RATE_LIMIT_PER_MINUTE = 120
PREFIX_LENGTH = 12
KEY_BYTES = 32


class ApiKeyRow(Base):
    """API-06. One issued key. `key_hash` is unique so a lookup is an
    index hit rather than a scan over every tenant's keys."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    owner_org: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)

    rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_RATE_LIMIT_PER_MINUTE
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def hash_key(raw_key: str) -> str:
    """SHA-256 hex digest. Plain SHA-256 rather than a slow KDF because
    an API key is 256 bits of CSPRNG output, not a human-chosen password
    — there is no dictionary to attack, and this runs on every request."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def create_api_key(
    session: Session,
    *,
    owner_org: str,
    name: str,
    rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
) -> tuple[str, ApiKeyRow]:
    """Issue a key. Returns (raw_key, row).

    The raw key is returned exactly once and never stored — the caller
    must show it to the operator now or lose it.
    """
    raw = f"sk_{secrets.token_urlsafe(KEY_BYTES)}"
    row = ApiKeyRow(
        owner_org=owner_org,
        name=name,
        key_hash=hash_key(raw),
        prefix=raw[:PREFIX_LENGTH],
        rate_limit_per_minute=rate_limit_per_minute,
    )
    session.add(row)
    session.flush()
    return raw, row


def resolve_api_key(session: Session, raw_key: str) -> ApiKeyRow | None:
    """Look up a live key. Revoked keys resolve to None."""
    stmt = select(ApiKeyRow).where(
        ApiKeyRow.key_hash == hash_key(raw_key), ApiKeyRow.revoked_at.is_(None)
    )
    return session.scalars(stmt).one_or_none()


# --------------------------------------------------------------------- #
# rate limiting
# --------------------------------------------------------------------- #

_redis_client: redis.Redis | None = None


def _redis() -> redis.Redis | None:
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.Redis.from_url(
                get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1
            )
        except redis.RedisError:
            return None
    return _redis_client


def check_rate_limit(key_id: str, limit_per_minute: int) -> tuple[bool, int]:
    """Fixed-window counter. Returns (allowed, remaining).

    Fails OPEN on any Redis problem — see the module docstring.
    """
    client = _redis()
    if client is None:
        return True, limit_per_minute

    window = int(datetime.now(UTC).timestamp() // 60)
    bucket = f"ratelimit:{key_id}:{window}"
    try:
        used = client.incr(bucket)
        if used == 1:
            client.expire(bucket, 120)
    except redis.RedisError:
        return True, limit_per_minute

    return used <= limit_per_minute, max(0, limit_per_minute - int(used))


# --------------------------------------------------------------------- #
# the dependency
# --------------------------------------------------------------------- #


def current_org(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    x_api_key: Annotated[str | None, Header()] = None,
    x_owner_org: Annotated[str | None, Header()] = None,
) -> str:
    """API-06. Resolve the calling tenant, or refuse the request.

    `X-Owner-Org` is still honoured when SOLARFIT_ALLOW_HEADER_TENANT is
    set, purely so the existing test suite and local demos keep working
    while keys are being issued. It is off by default and must never be
    enabled in a deployed environment — it lets any caller name any
    tenant.
    """
    settings = get_settings()

    if x_api_key:
        row = resolve_api_key(session, x_api_key)
        if row is None:
            # Same message for unknown and revoked: distinguishing them
            # tells an attacker which of their guesses used to be real.
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or revoked API key")

        allowed, remaining = check_rate_limit(str(row.id), row.rate_limit_per_minute)
        if not allowed:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"rate limit of {row.rate_limit_per_minute}/min exceeded",
                headers={"Retry-After": "60"},
            )

        row.last_used_at = datetime.now(UTC)
        request.state.api_key_id = str(row.id)
        request.state.rate_limit_remaining = remaining
        return row.owner_org

    if x_owner_org and settings.allow_header_tenant:
        return x_owner_org

    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "X-API-Key header required",
        headers={"WWW-Authenticate": "ApiKey"},
    )
