"""Owner: karthik (App Platform & Foundation).

Frontend-shaped site domain — wraps the existing, real
repositories/sites.py and routers/sites.py::create_site_core() (never
duplicating their logic) behind response models that match lib/types.ts
field-for-field. Every route requires current_user() and is scoped to
the caller's own owner_org.

Real, documented gaps in this pass, not silently guessed at:
  - Site.latestAssessment and CompositeSite.aggregateCapacityKwp need
    the `assessments` table, which is omkar's stream and doesn't exist
    yet — both return None/0 with a clear comment at the exact line
    that needs updating once his migration lands.
  - PortfolioSummary.activeJobs needs keerthana's `vendor_jobs` table,
    same situation — returns 0 until then.
  - getSiteHistory's "assessment" HistoryEvent kind is the same
    dependency — the union query below is written to be extended with
    one more branch, not restructured, once the table exists.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import select
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, current_user
from solarfit.db import get_session
from solarfit.domain.site import RoofSiteType, Site
from solarfit.providers import solar_api
from solarfit.repositories import calibration as calibration_repo
from solarfit.repositories import sites as repo
from solarfit.repositories import usn_uploads as usn_uploads_repo
from solarfit.routers.sites import SiteCreate, create_site_core

router = APIRouter(prefix="/app", tags=["app-sites"])

# The frontend's create-site flow doesn't collect a jurisdiction yet (no
# such field on its form) — every rooftop constraint pack is jurisdiction-
# scoped, so something must be stored. Defaults to the same example
# jurisdiction already used throughout this codebase's own fixtures until
# a real address->jurisdiction lookup or a form field exists.
_DEFAULT_JURISDICTION = "IN-TG"


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# --------------------------------------------------------------------- #
# response models
# --------------------------------------------------------------------- #


class GeoPointOut(_CamelModel):
    lat: float
    lng: float


class SiteOut(_CamelModel):
    id: str
    name: str
    site_type: str
    address: str
    district: str
    state: str
    location: GeoPointOut
    boundary: list[GeoPointOut] | None = None
    created_at: str
    updated_at: str
    latest_assessment: dict | None = None
    usn_status: str
    usn: str | None = None
    tags: list[str]


class CompositeSiteOut(_CamelModel):
    id: str
    name: str
    feeder_or_dt: str
    member_site_ids: list[str]
    aggregate_capacity_kwp: float
    created_at: str


class SupersededFieldOut(_CamelModel):
    field: str
    old_value: str
    new_value: str


class HistoryEventOut(_CamelModel):
    id: str
    site_id: str
    actor: str
    timestamp: str
    kind: str
    summary: str
    superseded_fields: list[SupersededFieldOut] | None = None


class SiteListOut(_CamelModel):
    items: list[SiteOut]
    total: int


class PortfolioSummaryOut(_CamelModel):
    total_sites: int
    total_capacity_kwp: float
    verdict_breakdown: dict[str, int]
    active_jobs: int
    site_type_breakdown: dict[str, int]


class AppSiteCreate(_CamelModel):
    name: str = Field(min_length=1, max_length=255)
    site_type: RoofSiteType
    address: str = Field(min_length=1)
    district: str = ""
    state: str = ""
    lat: float
    lng: float
    jurisdiction: str = _DEFAULT_JURISDICTION


class CompositeSiteCreate(_CamelModel):
    name: str = Field(min_length=1, max_length=255)
    feeder_or_dt: str = Field(min_length=1, max_length=255)
    member_site_ids: list[str] = Field(min_length=1)


# --------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------- #


def _boundary_points(site: Site) -> list[GeoPointOut] | None:
    if not site.boundary:
        return None
    coords = site.boundary["coordinates"][0]  # exterior ring
    # GeoJSON polygons repeat the first point as the last to close the
    # ring — the frontend's point list doesn't want that duplicate.
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords = coords[:-1]
    return [GeoPointOut(lat=c[1], lng=c[0]) for c in coords]


def _site_out(site: Site, row: repo.SiteRow) -> SiteOut:
    lng, lat = site.centroid["coordinates"]
    return SiteOut(
        id=site.id,
        name=site.name,
        site_type=site.site_type,
        address=row.address or "",
        district=row.district or "",
        state=row.state or "",
        location=GeoPointOut(lat=lat, lng=lng),
        boundary=_boundary_points(site),
        created_at=site.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
        # TODO(omkar): once the `assessments` table lands, look up this
        # site's most recent row from it here instead of None.
        latest_assessment=None,
        usn_status="confirmed" if site.usn else "not_started",
        usn=site.usn.usn if site.usn else None,
        tags=row.tags or [],
    )


def _owned_row_or_404(session: Session, site_id: str, owner_org: str) -> tuple[Site, repo.SiteRow]:
    """Same 404-not-403 reasoning as routers/sites.py::_owned_or_404 —
    confirming another tenant's site exists at all is itself a leak."""
    try:
        site = repo.get(session, site_id)
    except ValueError as exc:  # malformed UUID
        raise HTTPException(status.HTTP_404_NOT_FOUND, "site not found") from exc
    if site is None or site.owner_org != owner_org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "site not found")
    row = session.get(repo.SiteRow, uuid.UUID(site.id))
    return site, row


# --------------------------------------------------------------------- #
# endpoints
# --------------------------------------------------------------------- #


@router.get("/sites", response_model=SiteListOut)
def list_sites(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    q: Annotated[str | None, Query()] = None,
    site_type: Annotated[str | None, Query(alias="siteType")] = None,
    verdict: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(alias="pageSize", ge=1)] = None,
) -> SiteListOut:
    """Mirrors the mock client's listSites() filtering/pagination exactly
    (lib/api/client.ts) so the frontend's site-inventory page needs no
    changes to consume this for real. `verdict` always yields an empty
    match today — every site's latestAssessment is None until omkar's
    `assessments` table lands, which is the honest answer, not a bug."""
    if not user.owner_org:
        return SiteListOut(items=[], total=0)

    sites = repo.list_sites(session, owner_org=user.owner_org)
    items = []
    for s in sites:
        row = session.get(repo.SiteRow, uuid.UUID(s.id))
        items.append(_site_out(s, row))

    if q:
        needle = q.lower()
        items = [
            o
            for o in items
            if needle in o.name.lower()
            or needle in o.address.lower()
            or needle in o.district.lower()
            or needle in o.id.lower()
            or needle in (o.usn or "").lower()
        ]
    if site_type:
        items = [o for o in items if o.site_type == site_type]
    if state:
        items = [o for o in items if o.state == state]
    if verdict:
        items = [o for o in items if o.latest_assessment and o.latest_assessment.get("verdict") == verdict]

    total = len(items)
    size = page_size or total or 1
    start = (page - 1) * size
    return SiteListOut(items=items[start : start + size], total=total)


@router.get("/sites/portfolio-summary", response_model=PortfolioSummaryOut)
def get_portfolio_summary(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> PortfolioSummaryOut:
    sites = repo.list_sites(session, owner_org=user.owner_org) if user.owner_org else []

    site_type_breakdown: dict[str, int] = {}
    for s in sites:
        site_type_breakdown[s.site_type] = site_type_breakdown.get(s.site_type, 0) + 1

    return PortfolioSummaryOut(
        total_sites=len(sites),
        # TODO(omkar): sum each site's latest assessment.capacityKwp once
        # the `assessments` table exists — 0 is honest, not wrong, today.
        total_capacity_kwp=0.0,
        # TODO(omkar): tally verdicts from `assessments` the same way.
        verdict_breakdown={},
        # TODO(keerthana): count this owner_org's sites' vendor_jobs not
        # yet `submitted` once the `vendor_jobs` table exists.
        active_jobs=0,
        site_type_breakdown=site_type_breakdown,
    )


@router.get("/composites", response_model=list[CompositeSiteOut])
def list_composites(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> list[CompositeSiteOut]:
    if not user.owner_org:
        return []
    rows = repo.list_composite_sites(session, owner_org=user.owner_org)
    return [_composite_out(r) for r in rows]


@router.post("/composites", response_model=CompositeSiteOut, status_code=status.HTTP_201_CREATED)
def create_composite(
    payload: CompositeSiteCreate,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> CompositeSiteOut:
    if not user.owner_org:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only customer accounts can create composite sites")
    try:
        row = repo.create_composite_site(
            session,
            name=payload.name,
            feeder_or_dt=payload.feeder_or_dt,
            member_site_ids=payload.member_site_ids,
            owner_org=user.owner_org,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _composite_out(row)


def _composite_out(row: repo.CompositeSiteRow) -> CompositeSiteOut:
    return CompositeSiteOut(
        id=str(row.id),
        name=row.name,
        feeder_or_dt=row.feeder_or_dt,
        member_site_ids=row.member_site_ids,
        # TODO(omkar): sum each member's latest assessment.capacityKwp
        # once the `assessments` table exists.
        aggregate_capacity_kwp=0.0,
        created_at=row.created_at.isoformat(),
    )


@router.post("/sites", response_model=SiteOut, status_code=status.HTTP_201_CREATED)
def create_site(
    payload: AppSiteCreate,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SiteOut:
    """Wraps routers/sites.py::create_site_core() — same geometry
    resolution (address -> Solar API GEO-04, when resolvable) and
    SITE-02 validation as the existing POST /sites, just accepting the
    frontend's lat/lng-based input shape and returning its Site shape."""
    if not user.owner_org:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only customer accounts can create sites")

    core_payload = SiteCreate(
        site_type=payload.site_type,
        name=payload.name,
        jurisdiction=payload.jurisdiction,
        address=payload.address,
        centroid={"type": "Point", "coordinates": [payload.lng, payload.lat]},
    )
    try:
        site, _note = create_site_core(
            core_payload,
            session,
            user.owner_org,
            address=payload.address,
            district=payload.district or None,
            state=payload.state or None,
        )
    except solar_api.SolarApiError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    row = session.get(repo.SiteRow, uuid.UUID(site.id))
    return _site_out(site, row)


@router.get("/sites/{site_id}", response_model=SiteOut)
def get_site(
    site_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SiteOut:
    site, row = _owned_row_or_404(session, site_id, user.owner_org or "")
    return _site_out(site, row)


@router.get("/sites/{site_id}/history", response_model=list[HistoryEventOut])
def get_site_history(
    site_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> list[HistoryEventOut]:
    """Unions across every table that already records something that
    happened to this site — no new generic event table. Extend with one
    more branch (reading the `assessments` table) once omkar's stream
    lands; don't restructure this function to do it."""
    _site, _row = _owned_row_or_404(session, site_id, user.owner_org or "")

    events: list[HistoryEventOut] = []

    for v in repo.versions(session, site_id):
        kind = "created" if v.version_no == 1 else "boundary_edit"
        summary = (
            f"Site created via {v.source}" if kind == "created" else f"Boundary changed by {v.actor} ({v.source})"
        )
        superseded = None
        if kind == "boundary_edit":
            superseded = [SupersededFieldOut(field="boundary", old_value="(previous version)", new_value=f"version {v.version_no}")]
        events.append(
            HistoryEventOut(
                id=str(v.id),
                site_id=site_id,
                actor=v.actor,
                timestamp=v.created_at.isoformat(),
                kind=kind,
                summary=summary,
                superseded_fields=superseded,
            )
        )

    usn_rows = session.scalars(
        select(usn_uploads_repo.UsnOcrUpload).where(usn_uploads_repo.UsnOcrUpload.site_id == site_id)
    )
    for u in usn_rows:
        events.append(
            HistoryEventOut(
                id=u.id,
                site_id=site_id,
                actor=user.email,
                timestamp=u.uploaded_at.isoformat(),
                kind="usn_capture",
                summary=f"USN {u.document_type} upload — {u.extraction_status}",
            )
        )

    survey_rows = session.scalars(
        select(calibration_repo.CalibrationRecord).where(calibration_repo.CalibrationRecord.site_id == site_id)
    )
    for c in survey_rows:
        events.append(
            HistoryEventOut(
                id=c.id,
                site_id=site_id,
                actor=user.email,
                timestamp=c.created_at.isoformat(),
                kind="field_survey",
                summary=f"Field survey recorded {c.measured_area_m2:.1f} m² usable area",
            )
        )

    events.sort(key=lambda e: e.timestamp)
    return events
