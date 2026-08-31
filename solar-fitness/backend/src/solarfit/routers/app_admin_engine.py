"""Owner: karthik (App Platform & Foundation).

Admin-only routes over two engine functions that already existed, were
already tested, but had no way to actually be called — found during the
FRD spec-compliance audit's Phase 4:
  - CACHE-04's force_refresh(): repositories/analysis_cache.py
  - OBS-06's reject_applied_obstacle(): engine/obstacles.py

Its own router file, same reasoning as app_admin_platform.py's — small,
narrowly-scoped admin surfaces stay in their own files to avoid merge
collisions with omkar's/keerthana's admin routers.

OBS-05's "advisory obstacle review" (listing what's below the
auto-apply threshold, for admin promotion) is deliberately NOT included
here: no query function for it exists anywhere — detected obstacles
live inside a cached vision_refinement blob keyed by location, not
queryable by site, and there's no "promote" counterpart to
reject_applied_obstacle() either. Building that listing/promotion
capability is new feature work, not "expose what's already built,"
which is this file's whole scope.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, require_role
from solarfit.db import get_session
from solarfit.repositories import audit as audit_repo

router = APIRouter(prefix="/app/admin", tags=["app-admin-engine"])


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ForceRefreshRequest(_CamelModel):
    lat: float
    lng: float


class ForceRefreshResponse(_CamelModel):
    lat: float
    lng: float
    refreshed: bool = True


class RejectObstacleResponse(_CamelModel):
    site_id: str
    obstacle_id: str
    usable_area_m2: float | None = None


@router.post("/cache/force-refresh", response_model=ForceRefreshResponse)
def force_refresh_cache(
    payload: ForceRefreshRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> ForceRefreshResponse:
    """CACHE-04. Deletes the cached analysis for one rounded lat/long so
    the next assessment at this location recomputes it from scratch —
    the one explicit bypass CACHE-04 requires; reuse otherwise stays
    unconditional and indefinite by design (CACHE-04's other half)."""
    from solarfit.repositories.analysis_cache import force_refresh

    force_refresh(payload.lat, payload.lng)
    audit_repo.write_audit_log(
        session,
        actor=admin.email,
        action="platform.cache_force_refresh",
        target=f"{payload.lat},{payload.lng}",
        details=f"{admin.email} force-refreshed the cached analysis at ({payload.lat}, {payload.lng})",
    )
    return ForceRefreshResponse(lat=payload.lat, lng=payload.lng)


@router.post("/sites/{site_id}/obstacles/{obstacle_id}/reject", response_model=RejectObstacleResponse)
def reject_obstacle(
    site_id: str,
    obstacle_id: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> RejectObstacleResponse:
    """OBS-06. Reverses exactly one previously auto-applied obstacle —
    subtracts its own polygon from the site's exclusions (never the
    whole version's batch), versions forward (SITE-05: the apply and
    the reversal both stay visible in history, nothing is deleted), and
    recomputes usable area."""
    from solarfit.engine.area import compute_usable_area_m2
    from solarfit.engine.obstacles import reject_applied_obstacle

    try:
        updated_site = reject_applied_obstacle(site_id, obstacle_id, actor=admin.email)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    usable_area_m2 = compute_usable_area_m2(updated_site) if updated_site.boundary else None
    audit_repo.write_audit_log(
        session,
        actor=admin.email,
        action="obstacle.rejected",
        target=f"{site_id}:{obstacle_id}",
        details=f"{admin.email} rejected auto-applied obstacle {obstacle_id} on site {site_id}",
    )
    return RejectObstacleResponse(site_id=site_id, obstacle_id=obstacle_id, usable_area_m2=usable_area_m2)
