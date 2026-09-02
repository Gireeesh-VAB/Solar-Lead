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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, require_role
from solarfit.db import get_session
from solarfit.repositories import assessments as assessments_repo
from solarfit.repositories import audit as audit_repo
from solarfit.repositories import feature_flags as feature_flags_repo
from solarfit.repositories import service_api_keys as service_api_keys_repo
from solarfit.repositories import sites as sites_repo
from solarfit.repositories import usn_uploads as usn_uploads_repo

router = APIRouter(prefix="/app/admin", tags=["app-admin-platform"])

# No real per-provider call metering exists anywhere in this codebase —
# these are the four external services the frontend's own fixtures
# already name. `limit` stays an illustrative placeholder (not a
# configured quota) until real metering exists, but `used` below is
# computed from the closest real, honest proxy for each service rather
# than a hardcoded 0: site creation geocodes via Maps, an assessment
# calls both Solar and Weather, and a bill/payment-proof upload calls
# Vision OCR.
_QUOTA_LIMITS = [
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


class ServiceApiKeyOut(_CamelModel):
    service: str
    masked_value: str
    last_rotated_at: str | None


class FeatureFlagOut(_CamelModel):
    key: str
    label: str
    description: str
    enabled: bool


class SetFeatureFlagRequest(_CamelModel):
    enabled: bool


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
    action yet, which is the honest answer, not a gap in this query.
    Quota `used` figures are real counts of this month's activity used
    as an honest proxy for each provider — see _QUOTA_LIMITS above."""
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    incidents = [
        r
        for r in audit_repo.list_audit_log(session, action="platform.incident", limit=10_000)
        if r.created_at >= month_start
    ]

    sites_this_month = len(
        [s for s in sites_repo.list_sites(session, limit=10_000) if s.created_at >= month_start]
    )
    assessments_this_month = len(
        [
            a
            for a in assessments_repo.list_assessments(session, limit=10_000)
            if a.created_at >= month_start
        ]
    )
    vision_uploads_this_month = usn_uploads_repo.count_uploaded_since(session, month_start)

    used_by_service = {
        "Google Maps API": sites_this_month,
        "Google Solar API": assessments_this_month,
        "Google Cloud Vision API": vision_uploads_this_month,
        "Weather API": assessments_this_month,
    }

    return PlatformHealthOut(
        uptime_pct=99.9,
        incidents_this_month=len(incidents),
        quotas=[ApiQuotaOut(used=used_by_service[q["service"]], **q) for q in _QUOTA_LIMITS],
    )


@router.get("/api-keys", response_model=list[ServiceApiKeyOut])
def list_api_keys(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> list[ServiceApiKeyOut]:
    rows = service_api_keys_repo.list_keys(session)
    return [
        ServiceApiKeyOut(
            service=r.service,
            masked_value=r.masked_value,
            last_rotated_at=r.last_rotated_at.isoformat() if r.last_rotated_at else None,
        )
        for r in rows
    ]


@router.post("/api-keys/rotate", response_model=RotateApiKeyResponse)
def rotate_api_key(
    payload: RotateApiKeyRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> RotateApiKeyResponse:
    """Scoped interpretation, not a literal rotation: `payload.service`
    names an outbound provider (Google Maps/Solar/Vision/Weather) whose
    credentials live in `.env`, not a live-rotatable secret store — there
    is no real secret-rotation infrastructure to call. This regenerates
    the persisted masked display value and timestamps the request in
    service_api_keys, without claiming to rotate a credential that isn't
    actually rotatable yet.

    (A real tenant `ApiKeyRow` rotation — auth.py's actual API-key system
    — is a separate, smaller addition: a new revoke_api_key() alongside
    the existing create_api_key(), not built this round since no admin
    screen calls for it yet.)
    """
    row = service_api_keys_repo.rotate_key(session, payload.service)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown service")

    audit_repo.write_audit_log(
        session,
        actor=admin.email,
        action="platform.api_key_rotation_requested",
        target=payload.service,
        details=f"{admin.email} requested rotation for {payload.service}",
    )
    return RotateApiKeyResponse(service=payload.service, rotated_at=row.last_rotated_at.isoformat())


@router.get("/feature-flags", response_model=list[FeatureFlagOut])
def list_feature_flags(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> list[FeatureFlagOut]:
    rows = feature_flags_repo.list_flags(session)
    return [
        FeatureFlagOut(key=r.key, label=r.label, description=r.description, enabled=r.enabled) for r in rows
    ]


@router.patch("/feature-flags/{key}", response_model=FeatureFlagOut)
def set_feature_flag(
    key: str,
    payload: SetFeatureFlagRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> FeatureFlagOut:
    row = feature_flags_repo.set_enabled(session, key, payload.enabled)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown feature flag")

    audit_repo.write_audit_log(
        session,
        actor=admin.email,
        action="platform.feature_flag_toggled",
        target=key,
        details=f"{admin.email} set feature flag {key} to {payload.enabled}",
    )
    return FeatureFlagOut(key=row.key, label=row.label, description=row.description, enabled=row.enabled)
