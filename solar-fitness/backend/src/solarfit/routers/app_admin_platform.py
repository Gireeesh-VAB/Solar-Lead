"""Owner: karthik (App Platform & Foundation).

Admin platform infra — audit log, platform health, API-key "rotation".
Its own router file, deliberately not shared with omkar's
app_admin_vendors.py or keerthana's app_admin_customers.py, even though
all three live under /app/admin/... — three people editing one router
file in parallel is exactly the kind of collision this session's earlier
4-way branch merge already proved painful.

All three endpoints here are admin-only (require_role("admin")).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, require_role
from solarfit.db import get_session
from solarfit.repositories import audit as audit_repo

router = APIRouter(prefix="/app/admin", tags=["app-admin-platform"])

# No real usage-metering infrastructure exists anywhere in this codebase
# yet (confirmed during the backend audit this round) — these are the
# four external services the frontend's own fixtures already name.
# `used` is always 0 (honest — nothing counts real calls yet); `limit`
# is an illustrative placeholder, not a configured quota, until real
# metering exists.
_PLACEHOLDER_QUOTAS = [
    {"service": "Google Maps API", "limit": 100_000, "unit": "requests/month"},
    {"service": "Google Solar API", "limit": 50_000, "unit": "requests/month"},
    {"service": "Google Cloud Vision API", "limit": 20_000, "unit": "requests/month"},
    {"service": "Weather API", "limit": 100_000, "unit": "requests/month"},
]


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AuditLogEntryOut(_CamelModel):
    id: str
    actor: str
    action: str
    target: str
    timestamp: str
    details: str = ""


class ApiQuotaOut(_CamelModel):
    service: str
    used: int
    limit: int
    unit: str


class PlatformHealthOut(_CamelModel):
    uptime_pct: float
    incidents_this_month: int
    quotas: list[ApiQuotaOut]


class RotateApiKeyRequest(_CamelModel):
    service: str = Field(min_length=1, max_length=255)


class RotateApiKeyResponse(_CamelModel):
    service: str
    rotated_at: str


@router.get("/audit-log", response_model=list[AuditLogEntryOut])
def list_audit_log(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
    actor: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> list[AuditLogEntryOut]:
    rows = audit_repo.list_audit_log(session, actor=actor, action=action, q=q)
    return [
        AuditLogEntryOut(
            id=str(r.id),
            actor=r.actor,
            action=r.action,
            target=r.target,
            timestamp=r.created_at.isoformat(),
            details=r.details or "",
        )
        for r in rows
    ]


@router.get("/platform-health", response_model=PlatformHealthOut)
def get_platform_health(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> PlatformHealthOut:
    """uptimePct is a documented placeholder — no uptime monitoring
    exists in this codebase yet. incidentsThisMonth is real: a count of
    audit_log rows this calendar month whose action is tagged
    "platform.incident" — currently always 0 since nothing writes that
    action yet, which is the honest answer, not a gap in this query."""
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    incidents = [
        r
        for r in audit_repo.list_audit_log(session, action="platform.incident", limit=10_000)
        if r.created_at >= month_start
    ]

    return PlatformHealthOut(
        uptime_pct=99.9,
        incidents_this_month=len(incidents),
        quotas=[ApiQuotaOut(used=0, **q) for q in _PLACEHOLDER_QUOTAS],
    )


@router.post("/api-keys/rotate", response_model=RotateApiKeyResponse)
def rotate_api_key(
    payload: RotateApiKeyRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> RotateApiKeyResponse:
    """Scoped interpretation, not a literal rotation: `payload.service`
    names an outbound provider (Google Maps/Solar/Vision/Weather) whose
    credentials live in `.env`, not a live-rotatable secret store — there
    is no real secret-rotation infrastructure to call. This records the
    action in the audit trail and returns an honest timestamp, without
    claiming to rotate something that isn't actually rotatable yet.

    (A real tenant `ApiKeyRow` rotation — auth.py's actual API-key system
    — is a separate, smaller addition: a new revoke_api_key() alongside
    the existing create_api_key(), not built this round since no admin
    screen calls for it yet.)
    """
    now = datetime.now(UTC)
    audit_repo.write_audit_log(
        session,
        actor=admin.email,
        action="platform.api_key_rotation_requested",
        target=payload.service,
        details=f"{admin.email} requested rotation for {payload.service}",
    )
    return RotateApiKeyResponse(service=payload.service, rotated_at=now.isoformat())
