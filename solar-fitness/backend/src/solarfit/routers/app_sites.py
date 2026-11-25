"""Owner: karthik (App Platform & Foundation).

Frontend-shaped site domain — wraps the existing, real
repositories/sites.py and routers/sites.py::create_site_core() (never
duplicating their logic) behind response models that match lib/types.ts
field-for-field. Every route requires current_user() and is scoped to
the caller's own owner_org.

Site.latestAssessment, PortfolioSummary.totalCapacityKwp/verdictBreakdown/
activeJobs, CompositeSite.aggregateCapacityKwp, and getSiteHistory's
"assessment" event kind all originally shipped as documented 0/None
placeholders waiting on omkar's `assessments` table and keerthana's
`vendor_jobs` table — both landed via merge, and this file was updated
to read them for real (see repositories/assessments.py::get_latest_by_site/
to_frontend_assessment_dict, repositories/vendors.py::count_active_jobs_for_sites).
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
from solarfit.providers import manual, solar_api
from solarfit.providers.base import is_approximate
from solarfit.providers.validation import GeometryRejected
from solarfit.repositories import assessments as assessments_repo
from solarfit.repositories import calibration as calibration_repo
from solarfit.repositories import sites as repo
from solarfit.repositories import usn_uploads as usn_uploads_repo
from solarfit.repositories import vendors as vendors_repo
from solarfit.routers.assessments import FinancialEstimateOut, GenerationEstimateOut
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


class MonthlyConsumptionEntryOut(_CamelModel):
    month: str
    units_kwh: float


class ElectricalReadinessOut(_CamelModel):
    """A customer-safe SUBSET of the vendor's real, submitted
    ElectricalAssessment (routers/app_vendor.py) — same
    financial_estimate-style wiring (row column -> repository/router ->
    frontend type), never fabricated. None until a vendor has actually
    submitted electrical-assessment data for this site's survey job.

    Each field is a real signal derived from the vendor's own submitted
    values, not a literal 1:1 field rename — documented per field below
    since ElectricalAssessment has no boolean literally named e.g.
    "meter available":
    - meter_available: the vendor recorded where the meter is (a located,
      accessible meter), from ElectricalAssessment.meter_location.
    - panel_checked: the vendor recorded the main distribution board's
      location, from ElectricalAssessment.main_db_location.
    - earthing_available: ElectricalAssessment.earthing_available,
      verbatim — the one field that already is this exact boolean.
    - inverter_location_available: the vendor recorded a proposed
      inverter location, from the same job's SafetyAssessment.
      inverter_location (spec section 13's physical/fire-safety capture,
      same vendor visit, same VendorJobRow).
    - cable_route_available: the vendor recorded the existing cable
      condition/route, from ElectricalAssessment.cable_condition.
    """

    meter_available: bool | None = None
    panel_checked: bool | None = None
    earthing_available: bool | None = None
    inverter_location_available: bool | None = None
    cable_route_available: bool | None = None


class BindingConstraintOut(_CamelModel):
    name: str
    reason: str
    kind: str


class CacheProvenanceOut(_CamelModel):
    cache_hit: bool


class CeilingLedgerOut(_CamelModel):
    """One constraint the resolver weighed.

    `kwp` stays nullable and `status` is carried through: a ceiling that
    could not be evaluated is not a ceiling of zero, and flattening the
    two would tell a customer they are limited to nothing when the truth
    is that we have not checked yet."""

    label: str
    kwp: float | None = None
    kind: str = "physical"
    status: str = "ok"
    note: str = ""
    is_binding: bool = False


class AssessmentOut(_CamelModel):
    id: str
    site_id: str
    verdict: str
    capacity_kwp: float
    confidence: str
    # Enquiry workflow (repositories/assessments.py::raise_enquiry()) —
    # "not_submitted" until the customer explicitly raises an enquiry,
    # then "pending"/"approved"/"rejected" as an admin acts on it.
    # "not_applicable" for a verdict that was never eligible to begin
    # with. This is the customer-safe subset of admin's own
    # ReviewFieldsOut (routers/app_assessments.py) — no reviewer name,
    # no rejection reason, no vendor id; just enough for the result page
    # to gate the "Raise Enquiry" entry point and show its own status.
    review_status: str = "not_applicable"
    enquiry_submitted_at: str | None = None
    # Raw numeric alongside the tier label above — the label stays for
    # backward compatibility with whatever already reads `confidence`.
    # Both real: engine/fitness.py::score_fitness()'s own 0..1 figures,
    # rescaled to 0-100 here purely for a customer-facing "X/100" figure.
    score: float | None = None
    confidence_score: float | None = None
    # engine/fitness.py::FitnessResult.components — the per-factor
    # breakdown (capacity_adequacy, constraint_headroom, geometry_quality,
    # shading, generation_yield) behind `score` above. Each value is None
    # when that factor's input was unavailable.
    score_components: dict[str, float | None] = Field(default_factory=dict)
    # FIT-04 explainability — engine/fitness.py::FitnessResult's own
    # confidence_components (the real per-factor values blended into
    # `confidence_score` above) and confidence_explanation (deterministic,
    # template-generated sentences derived from them; index 0 is always
    # the overall summary, the rest are one sentence per factor).
    confidence_components: dict[str, float] = Field(default_factory=dict)
    confidence_explanation: list[str] = Field(default_factory=list)
    binding_constraint: BindingConstraintOut | None
    reasons: list[str]
    # Phase 6 — see domain/assessment.py::ConditionCode's docstring.
    conditions: list[dict] = Field(default_factory=list)
    ceiling_ledger: list[CeilingLedgerOut] = Field(default_factory=list)
    # CON-04 context for "how we worked this out". All three were already
    # stored on the row; only the plumbing to the frontend was missing.
    usable_area_m2: float | None = None
    # AREA-01, pre-setback/pre-exclusion. Paired with usable_area_m2 above
    # so the frontend can show total vs usable vs non-usable area, all
    # real numbers.
    total_area_m2: float | None = None
    max_technical_kwp: float | None = None
    headroom_kwp: float | None = None
    # engine/panel_packing.py's real layout, packed into the resolved
    # usable polygon and capped at capacity_kwp — see
    # routers/assessments.py::_pack_panel_layout(). None when nothing
    # could be packed (no usable area, no capacity, or Solar API/packing
    # failure) — never a fabricated layout standing in for a real one.
    panel_layout: dict | None = None
    # Building Insights' per-plane roof data (pitch/azimuth/area/sunshine
    # per segment) — see routers/assessments.py::_pack_panel_layout().
    roof_segments: dict | None = None
    # routers/assessments.py::_building_match_warning()'s coarse "does the
    # returned building match the customer's pin" check, when it fired.
    boundary_warning: str | None = None
    # engine/fitness.py::STANDARD_LIMITATIONS — the authoritative
    # pre-feasibility disclaimer, stored on every row since Day 0 but
    # previously never reaching this response.
    limitations: str | None = None
    panorama_url: str | None = None
    ml_suitability_score: float | None = None
    # engine/generation.py::estimate_generation_kwh()'s real output —
    # already persisted (AssessmentRow.generation) but never reached the
    # customer-facing shape until now.
    generation: GenerationEstimateOut | None = None
    # engine/financials.py's real output — an engine ESTIMATE (config-pack
    # cost/kWp, subsidy scheme, tariff), never a real vendor quote. See
    # FinancialEstimateOut's docstring.
    financial_estimate: FinancialEstimateOut | None = None
    cache: CacheProvenanceOut
    assessed_at: str
    model_version: str


def _assessment_out(row) -> AssessmentOut:
    data = assessments_repo.to_frontend_assessment_dict(row)
    # engine/fitness.py's own component dict keys (capacity_adequacy, ...)
    # are snake_case, an internal engine convention — _CamelModel's alias
    # generator only camelCases a model's OWN declared fields, never keys
    # inside a raw dict value, so this boundary needs its own conversion
    # to match every other field this API already returns as camelCase.
    score_components = {to_camel(k): v for k, v in (data.get("score_components") or {}).items()}
    confidence_components = {to_camel(k): v for k, v in (data.get("confidence_components") or {}).items()}
    return AssessmentOut(
        id=data["id"],
        site_id=data["site_id"],
        verdict=data["verdict"],
        capacity_kwp=data["capacity_kwp"],
        confidence=data["confidence"],
        review_status=data.get("review_status", "not_applicable"),
        enquiry_submitted_at=data.get("enquiry_submitted_at"),
        score=data.get("score"),
        confidence_score=data.get("confidence_score"),
        score_components=score_components,
        confidence_components=confidence_components,
        confidence_explanation=data.get("confidence_explanation") or [],
        binding_constraint=BindingConstraintOut(**data["binding_constraint"])
        if data["binding_constraint"]
        else None,
        reasons=data["reasons"],
        conditions=data.get("conditions") or [],
        ceiling_ledger=[CeilingLedgerOut(**entry) for entry in data["ceiling_ledger"]],
        usable_area_m2=data["usable_area_m2"],
        total_area_m2=data.get("total_area_m2"),
        max_technical_kwp=data["max_technical_kwp"],
        headroom_kwp=data["headroom_kwp"],
        panel_layout=data["panel_layout"],
        roof_segments=data["roof_segments"],
        boundary_warning=data["boundary_warning"],
        limitations=data.get("limitations"),
        panorama_url=data["panorama_url"],
        ml_suitability_score=data["ml_suitability_score"],
        generation=GenerationEstimateOut(**data["generation"]) if data.get("generation") else None,
        financial_estimate=FinancialEstimateOut(**data["financial_estimate"]) if data.get("financial_estimate") else None,
        cache=CacheProvenanceOut(**data["cache"]),
        assessed_at=data["assessed_at"],
        model_version=data["model_version"],
    )


class SiteOut(_CamelModel):
    id: str
    name: str
    site_type: str
    address: str
    district: str
    state: str
    location: GeoPointOut
    boundary: list[GeoPointOut] | None = None
    # GEO-09 provenance for the boundary above. Exposed because the
    # frontend cannot otherwise tell a traced roof from GEO-04's bounding
    # RECTANGLE, and drawing a rectangle as though it were the roof is
    # how panels end up beside a building instead of on it.
    geometry_source: str | None = None
    boundary_is_approximate: bool = True
    geometry_confidence: float | None = None
    # providers/solar_api.py::MaskVectorization.competing_regions — real
    # count of other candidate buildings the mask found near the pin,
    # not a guess. None when no mask lookup ran at all; 0 means the
    # lookup ran and found the pin's building unambiguous.
    competing_buildings_nearby: int | None = None
    # Never hidden, even when LOW/MEDIUM — a customer reading a panel
    # layout is entitled to know how current/detailed the imagery behind
    # it actually is.
    imagery_quality: str | None = None
    imagery_date: str | None = None
    # SHADE-01/02 — domain/site.py::ShadingEstimate. All None when
    # source == "unavailable" (any non-solar_api geometry source carries
    # no shading data) — never a guessed shading figure.
    shading_score: float | None = None
    sunshine_hours_per_year: float | None = None
    shading_source: str | None = None
    # OBS-04's real, applied exclusion polygons (setbacks + obstacles
    # already subtracted from the usable area) — one ring per polygon,
    # same GeoJSON-ring-to-point-list convention as `boundary` above.
    # None when the site has no exclusions at all yet.
    exclusions: list[list[GeoPointOut]] | None = None
    created_at: str
    updated_at: str
    latest_assessment: AssessmentOut | None = None
    usn_status: str
    usn: str | None = None
    tags: list[str]
    roof_type: str | None = None
    roof_material: str | None = None
    roof_slope: str | None = None
    roof_construction_year: int | None = None
    electricity_board: str | None = None
    consumer_number: str | None = None
    connection_type: str | None = None
    sanctioned_load_kw: float | None = None
    contract_demand_kva: float | None = None
    connected_load_kw: float | None = None
    monthly_consumption_kwh: list[MonthlyConsumptionEntryOut] = []
    battery_required: bool | None = None
    backup_required: bool | None = None
    required_backup_hours: float | None = None
    critical_loads: str | None = None
    # StartCheckWizard map-selection metadata (lat/lng/zoom/mapTypeId of
    # the confirmed view) — lets a later screen reproduce the exact same
    # satellite view on demand, per VIS-06's never-store-imagery policy.
    # None for every site created before this field existed, and for any
    # site not created through the map wizard.
    map_view_metadata: dict | None = None
    # repositories/vendors.py::get_latest_job_for_site() — the customer-
    # facing "vendor display" the survey-requested banner uses to say
    # something more specific than just "queued". Deliberately NOT the
    # vendor's name/contact details (a vendor hasn't agreed to be
    # contacted directly by the customer before/without going through
    # this app) — only the job's own lifecycle status. None when no
    # survey has ever been queued for this site.
    survey_job_status: str | None = None
    # See ElectricalReadinessOut's own docstring. None whenever no vendor
    # has submitted electrical-assessment data for this site yet — same
    # "absence is data" discipline as survey_job_status above.
    electrical_readiness: ElectricalReadinessOut | None = None


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
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    jurisdiction: str = _DEFAULT_JURISDICTION


class CompositeSiteCreate(_CamelModel):
    name: str = Field(min_length=1, max_length=255)
    feeder_or_dt: str = Field(min_length=1, max_length=255)
    member_site_ids: list[str] = Field(min_length=1)


class SaveBoundaryRequest(_CamelModel):
    points: list[GeoPointOut] = Field(min_length=3)


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


def _exclusion_rings(site: Site) -> list[list[GeoPointOut]] | None:
    """site.exclusions is a GeoJSON MultiPolygon — one exterior ring per
    polygon, same de-duplication _boundary_points() already applies to a
    single Polygon's ring."""
    if not site.exclusions:
        return None
    rings = []
    for polygon_coords in site.exclusions["coordinates"]:
        exterior = polygon_coords[0]
        if len(exterior) > 1 and exterior[0] == exterior[-1]:
            exterior = exterior[:-1]
        rings.append([GeoPointOut(lat=c[1], lng=c[0]) for c in exterior])
    return rings or None


def _electrical_readiness_out(survey_job) -> ElectricalReadinessOut | None:
    """See ElectricalReadinessOut's docstring for the field-by-field
    derivation. survey_job is a repositories.vendors.VendorJobRow | None
    — returns None unless the vendor has actually submitted an
    electrical assessment (never a checklist of guesses)."""
    if survey_job is None or not survey_job.electrical_assessment:
        return None
    electrical = survey_job.electrical_assessment
    safety = survey_job.safety_assessment or {}
    return ElectricalReadinessOut(
        meter_available=electrical.get("meter_location") is not None,
        panel_checked=electrical.get("main_db_location") is not None,
        earthing_available=electrical.get("earthing_available"),
        inverter_location_available=safety.get("inverter_location") is not None,
        cable_route_available=electrical.get("cable_condition") is not None,
    )


def _site_out(session: Session, site: Site, row: repo.SiteRow) -> SiteOut:
    lng, lat = site.centroid["coordinates"]
    latest = assessments_repo.get_latest_by_site(session, site.id)
    survey_job = vendors_repo.get_latest_job_for_site(session, site.id)
    return SiteOut(
        id=site.id,
        name=site.name,
        site_type=site.site_type,
        address=row.address or "",
        district=row.district or "",
        state=row.state or "",
        location=GeoPointOut(lat=lat, lng=lng),
        boundary=_boundary_points(site),
        geometry_source=site.geometry_source,
        # A site with no boundary at all is not "approximate", it is
        # absent — say False rather than implying a rough shape exists.
        boundary_is_approximate=is_approximate(site.geometry_source) if site.boundary else False,
        geometry_confidence=site.geometry_confidence,
        competing_buildings_nearby=site.competing_buildings_nearby,
        imagery_quality=site.imagery_quality,
        imagery_date=site.imagery_date.isoformat() if site.imagery_date else None,
        shading_score=site.shading.shading_score if site.shading else None,
        sunshine_hours_per_year=site.shading.sunshine_hours_per_year if site.shading else None,
        shading_source=site.shading.source if site.shading else None,
        exclusions=_exclusion_rings(site),
        created_at=site.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
        latest_assessment=_assessment_out(latest) if latest else None,
        usn_status="confirmed" if site.usn else "not_started",
        usn=site.usn.usn if site.usn else None,
        tags=row.tags or [],
        roof_type=row.roof_type,
        roof_material=row.roof_material,
        roof_slope=row.roof_slope,
        roof_construction_year=row.roof_construction_year,
        electricity_board=row.electricity_board,
        consumer_number=row.consumer_number,
        connection_type=row.connection_type,
        sanctioned_load_kw=row.sanctioned_load_kw,
        contract_demand_kva=row.contract_demand_kva,
        connected_load_kw=row.connected_load_kw,
        monthly_consumption_kwh=[MonthlyConsumptionEntryOut(**e) for e in (row.monthly_consumption_kwh or [])],
        battery_required=row.battery_required,
        backup_required=row.backup_required,
        required_backup_hours=row.required_backup_hours,
        critical_loads=row.critical_loads,
        map_view_metadata=row.map_view_metadata,
        survey_job_status=survey_job.status if survey_job else None,
        electrical_readiness=_electrical_readiness_out(survey_job),
    )


def _polygon_from_points(points: list[GeoPointOut]) -> dict:
    """Inverse of _boundary_points() above — closes the ring back up
    (repeats the first point as the last) the way GeoJSON requires and
    _boundary_points() itself strips off when reading."""
    coords = [[p.lng, p.lat] for p in points]
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


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
    changes to consume this for real. `verdict` filters against the real
    latest assessment now that the `assessments` table exists."""
    if not user.owner_org:
        return SiteListOut(items=[], total=0)

    sites = repo.list_sites(session, owner_org=user.owner_org)
    items = []
    for s in sites:
        row = session.get(repo.SiteRow, uuid.UUID(s.id))
        items.append(_site_out(session, s, row))

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
        items = [o for o in items if o.latest_assessment and o.latest_assessment.verdict == verdict]

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
    total_capacity_kwp = 0.0
    verdict_breakdown: dict[str, int] = {}
    for s in sites:
        site_type_breakdown[s.site_type] = site_type_breakdown.get(s.site_type, 0) + 1
        latest = assessments_repo.get_latest_by_site(session, s.id)
        if latest is not None:
            total_capacity_kwp += (latest.capacity or {}).get("recommended_kwp") or 0.0
            verdict_breakdown[latest.verdict] = verdict_breakdown.get(latest.verdict, 0) + 1

    active_jobs = vendors_repo.count_active_jobs_for_sites(session, [s.id for s in sites])

    return PortfolioSummaryOut(
        total_sites=len(sites),
        total_capacity_kwp=total_capacity_kwp,
        verdict_breakdown=verdict_breakdown,
        active_jobs=active_jobs,
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
    return [_composite_out(session, r) for r in rows]


@router.post("/composites", response_model=CompositeSiteOut, status_code=status.HTTP_201_CREATED)
def create_composite(
    payload: CompositeSiteCreate,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> CompositeSiteOut:
    if not user.owner_org:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "only customer accounts can create composite sites"
        )
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
    return _composite_out(session, row)


def _composite_out(session: Session, row: repo.CompositeSiteRow) -> CompositeSiteOut:
    aggregate_capacity_kwp = 0.0
    for member_id in row.member_site_ids:
        latest = assessments_repo.get_latest_by_site(session, member_id)
        if latest is not None:
            aggregate_capacity_kwp += (latest.capacity or {}).get("recommended_kwp") or 0.0
    return CompositeSiteOut(
        id=str(row.id),
        name=row.name,
        feeder_or_dt=row.feeder_or_dt,
        member_site_ids=row.member_site_ids,
        aggregate_capacity_kwp=aggregate_capacity_kwp,
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
    return _site_out(session, site, row)


@router.get("/sites/{site_id}", response_model=SiteOut)
def get_site(
    site_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SiteOut:
    """Real gap this closes: this endpoint used to be strictly
    owner_org-scoped, so an admin (owner_org=None) or a vendor
    (owner_org=None, tracked by vendor_id instead) could never read a
    customer's site at all — every vendor job detail page's `getSite()`
    call was silently failing and falling back to district/state only.
    Admins can read any site (matches every other admin-scoped GET in
    this codebase); a vendor can read exactly the sites they have an
    assigned job on, nothing else."""
    if user.role in ("admin", "vendor"):
        try:
            site = repo.get(session, site_id)
        except ValueError as exc:  # malformed UUID
            raise HTTPException(status.HTTP_404_NOT_FOUND, "site not found") from exc
        allowed = site is not None and (
            user.role == "admin"
            or (user.vendor_id is not None and vendors_repo.vendor_has_job_for_site(session, user.vendor_id, site_id))
        )
        if not allowed:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "site not found")
        row = session.get(repo.SiteRow, uuid.UUID(site.id))
        return _site_out(session, site, row)

    site, row = _owned_row_or_404(session, site_id, user.owner_org or "")
    return _site_out(session, site, row)


@router.put("/sites/{site_id}/boundary", response_model=SiteOut)
def save_boundary(
    site_id: str,
    payload: SaveBoundaryRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SiteOut:
    """Closes a real gap found during a frontend/backend sync audit:
    lib/api/client.ts's saveBoundary(siteId, points) had no matching
    route. GEO-07/08 validated the same way create_site_core validates a
    boundary at creation time (manual.resolve_manual), then persisted as
    a new SITE-05 version via repositories/sites.py::new_geometry_version()
    — never an overwrite, same discipline as every other geometry change."""
    site, _row = _owned_row_or_404(session, site_id, user.owner_org or "")

    boundary_geojson = _polygon_from_points(payload.points)
    try:
        validated = manual.resolve_manual(site, {"boundary": boundary_geojson})
    except GeometryRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    updated_site = repo.new_geometry_version(
        session,
        site_id,
        boundary=validated,
        actor=user.email,
        source="manual_edit",
        geometry_source="manual_polygon",
    )
    updated_row = session.get(repo.SiteRow, uuid.UUID(site_id))
    return _site_out(session, updated_site, updated_row)


@router.get("/sites/{site_id}/history", response_model=list[HistoryEventOut])
def get_site_history(
    site_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> list[HistoryEventOut]:
    """Unions across every table that already records something that
    happened to this site — no new generic event table."""
    _site, _row = _owned_row_or_404(session, site_id, user.owner_org or "")

    events: list[HistoryEventOut] = []

    for v in repo.versions(session, site_id):
        kind = "created" if v.version_no == 1 else "boundary_edit"
        summary = (
            f"Site created via {v.source}"
            if kind == "created"
            else f"Boundary changed by {v.actor} ({v.source})"
        )
        superseded = None
        if kind == "boundary_edit":
            superseded = [
                SupersededFieldOut(
                    field="boundary",
                    old_value="(previous version)",
                    new_value=f"version {v.version_no}",
                )
            ]
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
        select(usn_uploads_repo.UsnOcrUpload).where(
            usn_uploads_repo.UsnOcrUpload.site_id == site_id
        )
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
        select(calibration_repo.CalibrationRecord).where(
            calibration_repo.CalibrationRecord.site_id == site_id
        )
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

    assessment_rows = session.scalars(
        select(assessments_repo.AssessmentRow).where(
            assessments_repo.AssessmentRow.site_id == site_id
        )
    )
    for a in assessment_rows:
        events.append(
            HistoryEventOut(
                id=a.id,
                site_id=site_id,
                actor="system:assessment",
                timestamp=a.created_at.isoformat(),
                kind="assessment",
                summary=f"Assessment run — verdict {a.verdict}",
            )
        )

    events.sort(key=lambda e: e.timestamp)
    return events
