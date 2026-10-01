"""Owner: Person 1 (Site & Geometry).

§9.8 Interface — the site CRUD surface. Tenant-scoped: every read is
filtered by owner_org, every write is stamped with it.

API-06 auth lives in solarfit.auth: callers present an `X-API-Key`
header which resolves to the owning tenant, rate-limited per key. The
old `X-Owner-Org` header still works only when ALLOW_HEADER_TENANT is
set, for local development and the test suite.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from solarfit.auth import current_org
from solarfit.db import get_session
from solarfit.domain import schemas
from solarfit.domain.site import RoofSiteType, Site
from solarfit.engine.area import boundary_area_m2, compute_usable_area_m2
from solarfit.packs import config_pack
from solarfit.providers import manual, solar_api, validation
from solarfit.providers.validation import GeometryRejected
from solarfit.repositories import sites as repo

router = APIRouter(prefix="/sites", tags=["sites"])


# --------------------------------------------------------------------- #
# schemas
# --------------------------------------------------------------------- #


class SiteCreate(BaseModel):
    site_type: RoofSiteType
    name: str = Field(min_length=1, max_length=255)
    jurisdiction: str = Field(min_length=2, max_length=32, examples=["IN-TG"])

    address: str | None = Field(
        default=None,
        description=(
            "Street address. When given and no boundary is supplied, the site is "
            "geocoded and resolved via the Google Solar API (GEO-04), and its "
            "shading data is extracted in the same call (SHADE-01)."
        ),
    )
    centroid: dict | None = Field(
        default=None,
        description="GeoJSON Point. Defaults to the boundary's centroid when omitted.",
    )
    boundary: dict | None = Field(default=None, description="GeoJSON Polygon (GEO-02)")
    exclusions: Any | None = Field(
        default=None,
        description="GeoJSON MultiPolygon, Polygon, or a list of either (GEO-08)",
    )
    geometry_source: Literal["manual_polygon", "imported", "field_measured"] = "manual_polygon"

    # USN-05 / SITE-02. Accepted here ONLY so the schema check can reject
    # it on a non-billing-linked type. Dropping it silently (by leaving it
    # off the model) would let a caller believe a government site had
    # stored a consumer number when it had not — and would make the
    # prohibition unenforceable at the API boundary, which is the only
    # place it matters. Person 4 owns what a valid value looks like.
    usn: str | None = None
    usn_source: str | None = None


class SiteRead(BaseModel):
    """A site plus the numbers §9.3 derives from it.

    `usable_area_m2` is null when the site has no boundary yet — that is
    INSUFFICIENT_DATA, deliberately not zero. A zero here would let a
    geometry failure read as a genuine 'this roof is unusable' verdict.
    """

    site: Site
    current_version: int
    boundary_area_m2: float | None = None
    usable_area_m2: float | None = None
    resolution_note: str | None = Field(
        default=None,
        description=(
            "Why geometry is missing or degraded, when it is — e.g. no Solar API "
            "coverage at this location (GEO-04). Never silently empty."
        ),
    )


def _read(session: Session, site: Site, *, note: str | None = None) -> SiteRead:
    row = session.get(repo.SiteRow, uuid.UUID(site.id))
    boundary_area = usable = None
    if site.boundary:
        boundary_area = round(boundary_area_m2(site), 2)
        usable = round(compute_usable_area_m2(site), 2)
    return SiteRead(
        site=site,
        current_version=row.current_version if row else 0,
        boundary_area_m2=boundary_area,
        usable_area_m2=usable,
        resolution_note=note,
    )


# --------------------------------------------------------------------- #
# endpoints
# --------------------------------------------------------------------- #


def create_site_core(
    payload: SiteCreate,
    session: Session,
    owner_org: str,
    *,
    address: str | None = None,
    district: str | None = None,
    state: str | None = None,
    tags: list[str] | None = None,
    monthly_bill_low_inr: float | None = None,
    monthly_bill_high_inr: float | None = None,
    highest_consumption_kwh: float | None = None,
    lowest_consumption_kwh: float | None = None,
    roof_type: str | None = None,
    roof_material: str | None = None,
    roof_slope: str | None = None,
    roof_construction_year: int | None = None,
    electricity_board: str | None = None,
    consumer_number: str | None = None,
    connection_type: str | None = None,
    sanctioned_load_kw: float | None = None,
    contract_demand_kva: float | None = None,
    connected_load_kw: float | None = None,
    monthly_consumption_kwh: list[dict] | None = None,
    battery_required: bool | None = None,
    backup_required: bool | None = None,
    required_backup_hours: float | None = None,
    critical_loads: str | None = None,
) -> tuple[Site, str | None]:
    """The real work behind SITE-01 + GEO-02 — geometry resolution,
    GEO-07/08 validation, SITE-02 schema check, persistence. Pulled out
    of create_site() below so routers/app_sites.py's frontend-shaped
    POST /app/sites can share it rather than duplicate it — same
    behavior either way, this function's return value is the only
    thing that changed, callers just get (site, resolution_note)
    directly instead of it being folded into a SiteRead.

    address/district/state/tags (karthik addition) are keyword-only and
    optional — the existing POST /sites caller below never passes them,
    unaffected; routers/app_sites.py's frontend-shaped create does. The
    monthly bill pair is the same: only the customer check flow collects
    it, and a site created without it behaves exactly as before.

    The boundary goes through GEO-07/08 validation before it is stored —
    a rejected trace is a 422, never a silently repaired polygon.
    """
    boundary = payload.boundary
    exclusions = None
    centroid = payload.centroid
    geometry_source: str | None = payload.geometry_source
    shading = None
    imagery_quality = None
    imagery_date = None
    resolution_note = None
    competing_buildings_nearby: int | None = None

    # GEO-04 + SHADE-01. Only when the caller gave an address and no
    # geometry — a supplied boundary always wins, since every other
    # source outranks solar_api in base.PRECEDENCE. An address is what
    # signals "please go and find this roof"; a bare centroid does not,
    # and must not trigger a billed lookup on its own.
    if boundary is None and payload.address:
        try:
            if centroid:
                # Coordinates already known — the frontend's map pin gives
                # us these directly. Geocoding the address as well would
                # be a second billed call to convert an address into a
                # location we are already holding, and it would make the
                # whole flow depend on the Geocoding API for no benefit.
                lng, lat = centroid["coordinates"][0], centroid["coordinates"][1]
                result = solar_api.resolve_for_location(float(lat), float(lng))
            else:
                result = solar_api.resolve_for_address(payload.address)
        except solar_api.SolarApiError as exc:
            # Configuration/quota problems are ours, not the caller's.
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

        centroid = centroid or result.centroid
        shading = result.shading
        imagery_quality = result.imagery_quality
        imagery_date = result.imagery_date
        resolution_note = result.detail

        if result.usable:
            boundary = result.boundary
            geometry_source = "solar_api"

            # The boundary above is Google's bounding RECTANGLE, not a
            # traced roof outline — Building Insights does not return one
            # (verified against the live API, 2026-09-01). Measuring that
            # rectangle over-states a real roof badly: on a Banjara Hills
            # building it gave 227.7 m² against Google's own 127.1 m²
            # roof figure, a 79% over-estimate. Quoting a system twice the
            # size a roof can hold is exactly the kind of plausible-looking
            # wrong number §17 exists to prevent.
            #
            # So when Google reports its own roof area, that supersedes
            # the rectangle. The rectangle is still stored as the boundary
            # because downstream needs *a* shape (imagery cropping, map
            # display, an operator's starting point for a trace), but it
            # no longer decides the area.
            solar_area_m2 = result.roof_area_m2
            if solar_area_m2:
                resolution_note = (
                    f"area from Solar API roof stats ({solar_area_m2:.1f} m²); "
                    "stored boundary is Google's bounding box, not a traced "
                    "outline — trace it (GEO-02) or field-measure it (GEO-06) "
                    "to supersede this"
                )

            # GEO-04's real-outline upgrade: vectorise the Solar API's own
            # building mask instead of settling for the rectangle above.
            # A second, billed Data Layers call — worth it exactly once per
            # site creation, never repeated on every later assessment. Any
            # failure (no mask at this location/quality tier, a download
            # error, nothing vectorisable) falls back to the rectangle
            # already stored above; extract_roof_polygon_from_mask() never
            # raises, so this can never block site creation the rectangle
            # path already handles.
            mask_result = solar_api.extract_roof_polygon_from_mask(
                float(centroid["coordinates"][1]), float(centroid["coordinates"][0])
            )
            # A real, independent signal for "is the pin near more than
            # one building" — the mask's own disconnected-region count,
            # not a guess. Recorded regardless of whether a polygon was
            # selected: a customer whose pin sits between two buildings
            # is entitled to know that even when neither region was
            # close enough to trust as theirs.
            competing_buildings_nearby = mask_result.competing_regions
            if mask_result.polygon is not None:
                # Same disagreement guard as routers/app_checks.py::
                # resolve_building_at_point() — _select_building_region()
                # picks whichever mask region is nearest the query point,
                # independent of (and not cross-checked against) Building
                # Insights' own building match. Only trust it when it's
                # close enough to agree; otherwise a dense block can hand
                # a customer their neighbour's real-but-wrong outline
                # instead of their own building's coarser rectangle.
                mask_centroid = solar_api.polygon_centroid(mask_result.polygon)
                disagreement_m = solar_api.centroid_disagreement_m(mask_centroid, centroid)
                max_disagreement_m = float(config_pack.get_roof_mask_params()["max_pin_distance_m"])
                if disagreement_m is not None and disagreement_m > max_disagreement_m:
                    resolution_note = (
                        f"{resolution_note or ''} building mask found a region "
                        f"{disagreement_m:.1f}m from the resolved building centre — "
                        "too far to trust as the same building, kept the rectangle."
                    ).strip()
                else:
                    boundary = mask_result.polygon
                    geometry_source = "solar_api_mask"
                    # The mask region nearest the query point can legitimately
                    # be a different structure than Building Insights resolved
                    # (see solar_api.polygon_centroid()'s docstring) — recompute
                    # from the boundary actually being stored, never leave the
                    # earlier Building Insights centroid attached to this
                    # different shape.
                    centroid = mask_centroid or centroid
                    resolution_note = (
                        "boundary vectorised from the Solar API's own building mask — "
                        "a real outline, not a bounding box. Still fully automated: "
                        "trace it (GEO-02) or field-measure it (GEO-06) for a "
                        "human-verified shape."
                    )
        elif centroid is None:
            # No coverage AND no location: nothing to store at all.
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"could not resolve {payload.address!r} ({result.status}): "
                f"{result.detail or 'no detail'}",
            )
        else:
            # GEO-04: absent/sparse coverage is recorded, not fatal. The
            # site is created at its geocoded point with no boundary, and
            # an operator can trace one later (GEO-02 outranks this).
            geometry_source = None

    if boundary is not None:
        if centroid is None:
            centroid = validation.centroid_of(boundary)
        try:
            provisional = Site(
                id="pending",
                site_type=payload.site_type,
                name=payload.name,
                owner_org=owner_org,
                jurisdiction=payload.jurisdiction,
                centroid=centroid,
                created_at=datetime.now(UTC),
            )
            boundary = manual.resolve_manual(provisional, {"boundary": boundary})
            exclusions = manual.normalise_exclusions(payload.exclusions, boundary)
        except GeometryRejected as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc
    elif centroid is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="a site needs a centroid or a boundary to derive one from",
        )

    # SITE-07 — probable-duplicate detection, previously wired into bulk
    # import only (routers/imports.py::find_nearby_site); single-site
    # creation never ran this check at all. A hit doesn't block creation
    # here (there's no on_duplicate choice on this endpoint the way bulk
    # import has one) — it surfaces as a note, same "flag, don't guess"
    # discipline as every other resolution_note on this path.
    from solarfit.routers.imports import find_nearby_site

    duplicate = find_nearby_site(session, centroid, owner_org)
    if duplicate is not None:
        existing_site_id, distance_m = duplicate
        duplicate_note = (
            f"possible duplicate: existing site {existing_site_id} is {distance_m:.0f} m away"
        )
        resolution_note = (
            f"{resolution_note}; {duplicate_note}" if resolution_note else duplicate_note
        )

    confidence = (
        validation.geometry_confidence(
            source=geometry_source, imagery_date=imagery_date, boundary=boundary
        )
        if boundary
        else None
    )
    # GEO-04/GEO-09: a BASE-tier rectangle is materially worse than a
    # HIGH-tier one, and the confidence has to say so — otherwise P4's
    # FIT-04 treats them alike.
    if confidence is not None and imagery_quality == "BASE":
        confidence = round(max(0.0, confidence - 0.15), 3)

    # SITE-02 — validate against the type's registered schema before storing.
    try:
        schemas.validate_site_payload(
            {
                "site_type": payload.site_type,
                "name": payload.name,
                "owner_org": owner_org,
                "jurisdiction": payload.jurisdiction,
                "centroid": centroid,
                "boundary": boundary,
                "geometry_source": geometry_source,
                "geometry_confidence": confidence,
                "usn": payload.usn,
                "usn_source": payload.usn_source,
            }
        )
    except schemas.SchemaViolation as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    site = repo.create(
        session,
        site_type=payload.site_type,
        name=payload.name,
        owner_org=owner_org,
        jurisdiction=payload.jurisdiction,
        centroid=centroid,
        boundary=boundary,
        exclusions=exclusions,
        geometry_source=geometry_source if boundary else None,
        imagery_quality=imagery_quality,
        imagery_date=imagery_date,
        geometry_confidence=confidence,
        competing_buildings_nearby=competing_buildings_nearby,
        shading=shading,
        address=address,
        district=district,
        state=state,
        tags=tags,
        usn=payload.usn,
        usn_source=payload.usn_source,
        monthly_bill_low_inr=monthly_bill_low_inr,
        monthly_bill_high_inr=monthly_bill_high_inr,
        highest_consumption_kwh=highest_consumption_kwh,
        lowest_consumption_kwh=lowest_consumption_kwh,
        roof_type=roof_type,
        roof_material=roof_material,
        roof_slope=roof_slope,
        roof_construction_year=roof_construction_year,
        electricity_board=electricity_board,
        consumer_number=consumer_number,
        connection_type=connection_type,
        sanctioned_load_kw=sanctioned_load_kw,
        contract_demand_kva=contract_demand_kva,
        connected_load_kw=connected_load_kw,
        monthly_consumption_kwh=monthly_consumption_kwh,
        battery_required=battery_required,
        backup_required=backup_required,
        required_backup_hours=required_backup_hours,
        critical_loads=critical_loads,
        actor=owner_org,
    )
    return site, resolution_note


@router.post("", response_model=SiteRead, status_code=status.HTTP_201_CREATED)
def create_site(
    payload: SiteCreate,
    session: Annotated[Session, Depends(get_session)],
    owner_org: Annotated[str, Depends(current_org)],
) -> SiteRead:
    """SITE-01 + GEO-02. Create a site, optionally with a drawn boundary.
    Thin wrapper over create_site_core() — see that function for the
    actual logic."""
    site, resolution_note = create_site_core(payload, session, owner_org)
    return _read(session, site, note=resolution_note)


@router.get("", response_model=list[SiteRead])
def list_sites(
    session: Annotated[Session, Depends(get_session)],
    owner_org: Annotated[str, Depends(current_org)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SiteRead]:
    sites = repo.list_sites(session, owner_org=owner_org, limit=limit, offset=offset)
    return [_read(session, s) for s in sites]


@router.get("/{site_id}", response_model=SiteRead)
def get_site(
    site_id: str,
    session: Annotated[Session, Depends(get_session)],
    owner_org: Annotated[str, Depends(current_org)],
) -> SiteRead:
    site = _owned_or_404(session, site_id, owner_org)
    return _read(session, site)


@router.get("/{site_id}/versions")
def get_site_versions(
    site_id: str,
    session: Annotated[Session, Depends(get_session)],
    owner_org: Annotated[str, Depends(current_org)],
) -> list[dict]:
    """SITE-05. Full geometry history, oldest first — append-only."""
    _owned_or_404(session, site_id, owner_org)
    return [
        {
            "version_no": v.version_no,
            "geometry_source": v.geometry_source,
            "actor": v.actor,
            "source": v.source,
            "note": v.note,
            "created_at": v.created_at,
        }
        for v in repo.versions(session, site_id)
    ]


def _owned_or_404(session: Session, site_id: str, owner_org: str) -> Site:
    """404 rather than 403 for another tenant's site — a 403 confirms the
    id exists, which is itself a cross-tenant leak."""
    try:
        site = repo.get(session, site_id)
    except ValueError as exc:  # malformed UUID
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found") from exc
    if site is None or site.owner_org != owner_org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")
    return site
