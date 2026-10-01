"""Owner: Person 4 (Scoring, USN & Assessment API).

Implements the core-assessment slice of §9.8 Interface (API-01..05) of
Solar_Fitness_Engine_Development_Document_v1.2 — tasks 12 and 13 of
Person 4's list in Rooftop_Backend_Implementation_Plan.html:

  Task 12 (API-01/02): orchestration endpoint combining Person 1/2/3's
    outputs into the single response shape, with vision_refinement/
    panorama_url/ml_suitability_score/cache_hit as optional additive
    fields; synchronous cache-hit path.
  Task 13 (API-03/04/05): async batch submission with pollable status;
    engine/pack version stamped on every response; versioned API path.

Two corrections found by re-reading the frozen contracts directly
(superseding earlier phases' assumptions):
  - CapacityResult has no pack_version field — constraint_pack_version
    comes from packs.config_pack.pack_version() instead.
  - AnalysisResult has no weather field — record_training_sample() (see
    below) fetches weather separately via providers.weather.fetch_weather()
    rather than trying to pull it off the cached analysis.

This is deliberately the last piece wired to real implementations — it
calls directly into every other person's still-stub module with no
try/except NotImplementedError anywhere, matching the rest of this
codebase's philosophy: a not-yet-built dependency should raise loudly,
not be silently worked around. Tests monkeypatch every dependency, same
discipline as engine/fitness.py, providers/usn_ocr.py, and
repositories/calibration.py's own test suites.

USN capture's HTTP surface (upload/confirm endpoints) is NOT part of
tasks 12/13 and stays out of scope here — a real, still-open gap, not
silently absorbed into this router.

Depends on: solarfit.domain.assessment.AnalysisResult (frozen, Day 0),
solarfit.repositories.analysis_cache.get_or_create_analysis (Person 3),
solarfit.packs.{universal,rooftop} + engine.resolver + engine.generation
(Person 2), solarfit.engine.fitness / engine.ml_score /
repositories.calibration (this person's own modules).
"""

import logging
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from pyproj import Transformer
from shapely.geometry import shape as shapely_shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

from solarfit import __version__ as engine_version
from solarfit.auth import current_org
from solarfit.db import session_scope
from solarfit.domain.assessment import Condition, FitnessVerdict, VisionRefinement
from solarfit.domain.constraint import CapacityResult
from solarfit.domain.site import RoofSiteType, Site, UsnCapture
from solarfit.engine import (
    financials,
    fitness,
    generation,
    panel_packing,
    panel_validation,
    resolver,
)
from solarfit.engine import ml_score as ml_score_engine
from solarfit.engine.area import (
    UsableRoof,
    boundary_area_m2,
    compute_usable_roof,
    exclusions_metric_geometry,
)
from solarfit.engine.consumption import estimate_annual_consumption
from solarfit.engine.projection import to_metric
from solarfit.packs import config_pack, rooftop, universal
from solarfit.packs.config_pack import pack_version
from solarfit.providers import solar_api
from solarfit.providers import weather as weather_provider
from solarfit.providers.base import outranks
from solarfit.providers.validation import GeometryRejected
from solarfit.providers.vision import fetch_building_insights
from solarfit.repositories import analysis_cache as analysis_cache_repo
from solarfit.repositories import calibration
from solarfit.repositories import sites as sites_repo
from solarfit.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/assessments", tags=["assessments"])


class SiteNotFoundError(Exception):
    pass


# Phase 4 — real backend-driven progress for the customer's processing
# screen. Machine-readable keys, in the order orchestrate_assessment()
# actually executes them; the frontend owns the human-facing copy for
# each (same "backend emits symbolic keys, frontend renders copy"
# pattern the verdict/status enums elsewhere in this codebase already
# use). Kept as one ordered list so a caller building a progress bar can
# also compute "how far through" a given stage is, not just its name.
ASSESSMENT_STAGES: list[str] = [
    "resolving_location",
    "analyzing_roof_imagery",
    "detecting_obstacles",
    "computing_usable_area",
    "sizing_system",
    "placing_panels",
    "scoring_feasibility",
    "finalizing_result",
]


class GenerationEstimateOut(BaseModel):
    """Persists engine/generation.py::estimate_generation_kwh()'s real
    output — previously computed on every assessment (it feeds
    fitness.score_fitness()) and then silently discarded, never stored
    or exposed. Backs the admin review page's "System Sizing" panel.

    camelCase aliasing (matching app_assessments.py's _CamelModel,
    duplicated here rather than imported to avoid a routers/assessments.py
    -> routers/app_assessments.py dependency the other direction doesn't
    have) — this model nests inside AppAssessmentResponse, and a nested
    model's OWN fields don't inherit the outer model's alias_generator,
    so without this every other field on this response is camelCase
    except these, silently."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    estimated_kwh_per_year: float | None
    specific_yield_kwh_per_kwp: float | None
    performance_ratio: float | None
    method: str
    method_notes: str
    p50_kwh_per_year: float | None = None
    p90_kwh_per_year: float | None = None
    pvgis_annual_kwh: float | None = None
    pvgis_monthly_kwh: list[float] | None = None


class FinancialEstimateOut(BaseModel):
    """Persists engine/financials.py::estimate_financials()'s real
    output — an ENGINE ESTIMATE, distinct from the admin-owned
    financial_feasibility real quote (routers/app_assessments.py::
    FinancialFeasibilityOut). Same camelCase-aliasing duplication
    reasoning as GenerationEstimateOut above."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    panel_cost_inr: float | None
    inverter_cost_inr: float | None
    mounting_structure_cost_inr: float | None
    electrical_material_cost_inr: float | None
    installation_cost_inr: float | None
    total_project_cost_inr: float | None
    subsidy_applicable: bool
    subsidy_category: str | None
    subsidy_amount_inr: float | None
    # FIN-01 subsidy explainability — see engine/financials.py::
    # _explain_subsidy()'s docstring. subsidy_scheme_max_amount_inr is
    # the scheme-wide maximum (shown even when this customer isn't
    # eligible, so "maximum available" and "your eligible amount" are
    # never conflated); subsidy_ineligibility_reason is set only when
    # subsidy_applicable is False; subsidy_explanation is deterministic,
    # template-generated sentences, empty when not applicable.
    #
    # All default to None/empty — an assessment persisted before this
    # explainability feature shipped has a financial_estimate JSON blob
    # with none of these keys at all, and reloading it (e.g. the admin
    # assessments list) must not 500 just because older data predates a
    # later-added, purely additive field.
    subsidy_scheme_name: str | None = None
    subsidy_scheme_max_amount_inr: float | None = None
    subsidy_rate_inr_per_kwp: float | None = None
    subsidy_scheme_max_capacity_kwp: float | None = None
    subsidy_capacity_considered_kwp: float | None = None
    subsidy_ineligibility_reason: str | None = None
    subsidy_explanation: list[str] = []
    customer_contribution_inr: float | None
    monthly_savings_inr: float | None
    annual_savings_inr: float | None
    payback_period_years: float | None
    ten_year_savings_inr: float | None
    twenty_year_savings_inr: float | None
    estimated_system_lifetime_years: float | None
    method_notes: str


class AssessmentResponse(BaseModel):
    site_id: str
    site_type: RoofSiteType

    verdict: FitnessVerdict
    score: float | None
    confidence: float
    # FIT-04 explainability — see domain/assessment.py::FitnessResult's
    # docstring for these two fields.
    confidence_components: dict[str, float] = {}
    confidence_explanation: list[str] = []
    binding_constraint: str
    reasons: list[str]
    # Phase 6 — see domain/assessment.py::ConditionCode's docstring.
    # fitness.score_fitness()'s own conditions (missing-data reasons,
    # gates, shading) plus WRONG_BUILDING_RETURNED, appended below when
    # _building_match_warning() fired — that check runs outside
    # score_fitness()'s own inputs, so it can't detect it itself.
    conditions: list[Condition] = []
    limitations: str

    capacity: CapacityResult
    boundary: dict
    usable_area_m2: float | None
    # AREA-01, pre-setback/pre-exclusion — the roof's raw boundary area.
    # usable_area_m2 above is what's left after setback+exclusions; the
    # difference is real, displayable "non-usable" area, not a guess.
    total_area_m2: float | None = None
    # engine/fitness.py::score_fitness()'s own FitnessResult.components —
    # the per-factor breakdown (capacity_adequacy, constraint_headroom,
    # geometry_quality, shading, generation_yield) behind the single
    # blended `score` above. Each value is None when that factor's input
    # was unavailable (never a fabricated number standing in for it).
    score_components: dict[str, float | None] = {}

    # Panels this app itself packed into the resolved usable polygon,
    # capped at `capacity.recommended_kwp` — see _pack_panel_layout()'s
    # docstring. None when there was nothing to pack (no usable polygon,
    # no resolved capacity, or Solar API/packing failure).
    panel_layout: dict | None = None
    # Building Insights' per-plane roof data (index, pitch, azimuth, area,
    # sunshine, plane height) — see _pack_panel_layout()'s docstring. None
    # when there was nothing to pack against.
    roof_segments: dict | None = None
    # A coarse "does the returned building match the pin" sanity check —
    # see _building_match_warning(). None when the check couldn't run or
    # found no mismatch.
    boundary_warning: str | None = None

    # Optional, additive per API-01 — never required, never displacing the above.
    vision_refinement: VisionRefinement | None = None
    panorama_url: str | None = None
    ml_suitability_score: float | None = None
    ml_model_version: str | None = None
    cache_hit: bool = False
    reused_from_analysis_id: str | None = None
    usn: UsnCapture | None = None
    generation: GenerationEstimateOut | None = None
    financial_estimate: FinancialEstimateOut | None = None

    engine_version: str  # API-04
    constraint_pack_version: str  # API-04


def _collect_ceilings_and_gates(
    site, usable_area_m2: float, annual_consumption_kwh: float | None = None
) -> tuple[list, list]:
    """Rooftop-only product — both packs apply uniformly, no site-type
    conditionals here (matches §17's resolver discipline).

    `annual_consumption_kwh` is CON-05's input, derived from the
    customer's own bill by engine/consumption.py. Passing None leaves
    consumption_offset at insufficient_data, which is what every
    assessment did before a bill could be captured: the system was then
    sized by roof area alone, and a household came back at tens of kWp it
    could never use.
    """
    consumption_params = (
        {"annual_consumption_kwh": annual_consumption_kwh}
        if annual_consumption_kwh is not None
        else {}
    )
    ceilings = [
        universal.usable_area_ceiling(site, usable_area_m2),
        universal.evacuation_headroom_ceiling(site, {}),
        rooftop.net_metering_cap(site, {}),
        rooftop.consumption_offset_ceiling(site, consumption_params),
        rooftop.transformer_headroom_ceiling(site, {}),
        rooftop.subsidy_tier_cap(site, {}),  # already reads site.usn internally
    ]
    gates = [
        universal.minimum_viable_size_gate(site, usable_area_m2),
        rooftop.structural_gate(site, {}),
    ]
    return ceilings, gates


# Generous on purpose: buildings vary widely in footprint, and the Solar
# API resolving to a real neighbour a pin's own building-width away is
# ordinary, not a fault. This only catches the case where the returned
# building plausibly ISN'T anywhere near the pin at all.
_BUILDING_MATCH_MARGIN_DEG = 0.0006  # roughly 65m at the equator


def _building_match_warning(lat: float, lng: float, insights: dict) -> str | None:
    """Coarse sanity check: does the returned Building Insights response
    plausibly correspond to the roof the customer actually pinned?

    The Solar API resolves buildingInsights:findClosest to whatever
    building is nearest the query point — an imprecisely placed pin, or a
    row of closely-spaced buildings, can silently return a neighbour's
    roof instead of the intended one. This is a bounding-box-plus-margin
    check against the pin, not survey-grade validation — it exists to
    catch a clear miss, not to certify a close one."""
    bbox = insights.get("boundingBox") or {}
    sw, ne = bbox.get("sw") or {}, bbox.get("ne") or {}
    lat_min, lat_max = sw.get("latitude"), ne.get("latitude")
    lng_min, lng_max = sw.get("longitude"), ne.get("longitude")
    if None in (lat_min, lat_max, lng_min, lng_max):
        return None

    inside = (
        lat_min - _BUILDING_MATCH_MARGIN_DEG <= lat <= lat_max + _BUILDING_MATCH_MARGIN_DEG
        and lng_min - _BUILDING_MATCH_MARGIN_DEG <= lng <= lng_max + _BUILDING_MATCH_MARGIN_DEG
    )
    if inside:
        return None
    return (
        "The rooftop data returned may be for a neighbouring building rather "
        "than your exact pin. If the roof shown below doesn't look right, "
        "reposition the pin more precisely on your building and check again."
    )


def _segment_quality_score(segment: dict) -> float:
    """Ranks roof planes for panel-selection priority when the roof holds
    more capacity than the customer's recommended system needs — the
    best-performing plane fills first, never an arbitrary segment order.

    Prefers the segment's own median sunshine quantile (Building
    Insights' real per-segment irradiance estimate, under `stats`) when
    available. Falls back to a south-facing/moderate-pitch heuristic —
    still built entirely from real per-segment fields, never a guessed
    weighting — only when sunshine data is absent.
    """
    quantiles = ((segment.get("stats") or {}).get("sunshineQuantiles")) or []
    if quantiles:
        return float(quantiles[len(quantiles) // 2])

    azimuth, pitch = segment.get("azimuthDegrees"), segment.get("pitchDegrees")
    if azimuth is None or pitch is None:
        return 0.0
    raw = abs(float(azimuth) - 180.0) % 360.0
    circular_diff = min(raw, 360.0 - raw)
    south_closeness = 1.0 - circular_diff / 180.0
    pitch_closeness = 1.0 - min(abs(float(pitch) - 20.0), 40.0) / 40.0
    return south_closeness * 0.7 + pitch_closeness * 0.3


def _segment_polygon_metric(segment: dict, usable_roof: UsableRoof):
    """This roof plane's share of the resolved usable polygon.

    Building Insights gives each segment its own axis-aligned
    boundingBox, not a per-segment outline — intersecting that box with
    usable_roof.polygon_metric (this app's own post-boundary,
    post-setback, post-exclusion polygon) is the best per-segment spatial
    signal the API actually exposes. Returns None when the segment has no
    boundingBox, or no real overlap with the usable roof (e.g. a segment
    that's entirely inside a setback or an excluded area).
    """
    bbox = segment.get("boundingBox")
    if not bbox or usable_roof.polygon_metric is None:
        return None
    try:
        box_geojson = solar_api.bounding_box_to_polygon(bbox)
    except GeometryRejected:
        return None
    box_metric, _ = to_metric(shapely_shape(box_geojson), epsg=usable_roof.epsg)
    intersection = usable_roof.polygon_metric.intersection(box_metric)
    if intersection.is_empty or intersection.area <= 0:
        return None
    return intersection


def _metric_polygon_to_wgs84_ring(geom: BaseGeometry, epsg: int) -> list[list[float]] | None:
    """A projected-CRS polygon -> a single (lng, lat) exterior ring, for
    drawing on a map. Same reprojection pattern as engine/panel_packing.py
    ::to_wgs84_rings(), for a standalone polygon instead of a packed
    layout's panels. None for anything that isn't a plain Polygon (a
    segment/usable-roof intersection can in principle produce a
    MultiPolygon on a re-entrant shape — drawing only one part of a
    building plane would misrepresent it, so this degrades to "no
    polygon" rather than silently picking one piece)."""
    if geom.geom_type != "Polygon":
        return None
    to_wgs84 = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True).transform
    return [list(point) for point in shapely_transform(to_wgs84, geom).exterior.coords]


def _pack_fallback_single_plane(
    usable_roof: UsableRoof,
    capacity: CapacityResult,
    lat: float,
    exclusions_metric: BaseGeometry | None,
) -> dict | None:
    """Packs the WHOLE usable polygon as one plane when Building Insights
    has no per-segment data to pack against (manually-drawn/imported
    boundaries, or any site Google's own imagery doesn't cover).

    Reuses pack_panels_best_orientation() unchanged — tilt_deg/azimuth_deg
    are left None so its own config-pack-default fallback applies, exactly
    the same defaulting pack_panels() already does for a real segment
    missing that data. `roof_segments` has no equivalent here (there is no
    per-plane Building Insights data to report), which the caller handles.
    """
    layout = panel_packing.pack_panels_best_orientation(
        usable_roof.polygon_metric, latitude_deg=lat
    )
    selected = panel_packing.select_for_target_capacity(layout, capacity.recommended_kwp)
    rings = panel_packing.to_wgs84_rings(selected, usable_roof.epsg)
    if not rings:
        return {"status": "no_layout", "reason": "No panels fit the usable roof area", "panels": []}

    validation = panel_validation.validate_layout(
        selected, usable_roof.polygon_metric, exclusions_metric
    )
    return {
        "status": "ok",
        "orientation": selected.orientation.upper(),
        "panelWatts": selected.panel_watts,
        "panelCount": selected.count,
        "totalKwp": round(selected.kwp, 2),
        "panels": [
            {
                "corners": [list(point) for point in ring],
                "segmentIndex": None,
                "azimuthDeg": selected.azimuth_deg,
                "tiltDeg": selected.tilt_deg,
            }
            for ring in rings
        ],
        "validation": {
            "panelCount": validation.panel_count,
            "rejectedCount": validation.rejected_count,
            "panelsOutsideRoof": validation.panels_outside_roof,
            "panelsIntersectingObstacles": validation.panels_intersecting_obstacles,
        },
    }


def _pack_panel_layout(
    usable_roof: UsableRoof,
    capacity: CapacityResult,
    lat: float,
    lng: float,
    site: Site | None = None,
) -> tuple[dict | None, dict | None, str | None]:
    """Packs real panels into the resolved usable polygon (post-setback,
    post-exclusion — engine/area.py's own output), capped at the
    customer's RECOMMENDED capacity, never the roof's technical maximum
    (CON-07: a bigger roof is not license to install a bigger system than
    the customer asked for).

    Every Building Insights roof plane (roofSegmentStats) is packed
    independently against ITS OWN tilt/azimuth and its own share of the
    usable polygon (see _segment_polygon_metric()) — never one shared
    orientation forced across the whole roof. Planes are filled
    best-first (see _segment_quality_score()) until the target capacity
    is reached, so a shaded or badly-oriented plane is never preferred
    over a better one just because it happened to be packed first. Each
    plane also tries both portrait and landscape (pack_panels_best_
    orientation()) and keeps whichever fits more panels.

    When Building Insights has no roof planes at all, the whole usable
    polygon is packed as a single plane instead of giving up (see
    _pack_fallback_single_plane()) — an irregular or manually-drawn roof
    with no Google segment data still gets a real layout.

    Replaces drawing Google's raw solarPanels[] array verbatim: those
    panels are fitted to Google's own building footprint, which has no
    relationship to this app's resolved boundary, obstacles, or usable
    area, and is the confirmed cause of panels appearing outside the roof
    or across excluded areas.

    `site`, when given, lets this attach a real panels-intersecting-
    obstacles count to the validation block (see engine/panel_validation)
    by reading the site's own unioned exclusion polygon. Optional and
    additive — every existing direct caller that doesn't pass one still
    gets a full panels-outside-roof check, just with obstacle-intersection
    always reported as zero rather than fabricated.

    Never raises — a Building Insights or packing failure degrades to
    (None, None, None), same "absence is data, not an exception"
    discipline every other Solar API consumer in this codebase already
    follows. Returns (panel_layout_dict, roof_segments_dict, boundary_warning).
    """
    if usable_roof.polygon_metric is None or not capacity.recommended_kwp:
        return None, None, None

    exclusions_metric = exclusions_metric_geometry(site) if site is not None else None

    try:
        insights = fetch_building_insights(lat, lng)
    except Exception:
        logger.warning(
            "Building Insights unavailable for panel packing at (%s, %s)", lat, lng, exc_info=True
        )
        return None, None, None
    if not insights:
        return None, None, None

    warning = _building_match_warning(lat, lng, insights)

    potential = insights.get("solarPotential") or {}
    segments = potential.get("roofSegmentStats") or []
    if not segments:
        return _pack_fallback_single_plane(usable_roof, capacity, lat, exclusions_metric), None, warning

    # Google's own module dimensions/wattage are preferred when given —
    # same "real data over configured defaults" rule panel_layout.py and
    # panel_packing.py's own docstring already establish.
    panel_kwargs: dict = {}
    if potential.get("panelHeightMeters"):
        panel_kwargs["panel_length_m"] = float(potential["panelHeightMeters"])
    if potential.get("panelWidthMeters"):
        panel_kwargs["panel_width_m"] = float(potential["panelWidthMeters"])
    if potential.get("panelCapacityWatts"):
        panel_kwargs["panel_watts"] = float(potential["panelCapacityWatts"])

    # Each segment's own polygon (boundingBox intersected with the
    # resolved usable roof — see _segment_polygon_metric()'s docstring),
    # computed once here and reused by the packing loop below instead of
    # recomputing it per segment. Persisted as WGS84 rings so the map can
    # draw each roof plane as its own coloured region (Step 14) instead
    # of only the shared roof-boundary outline it draws today — None
    # when the segment has no boundingBox or no real overlap with the
    # usable roof, same as everywhere else this polygon is used.
    segment_polygons_metric = [_segment_polygon_metric(segment, usable_roof) for segment in segments]

    # Persisted regardless of whether packing succeeds — real per-plane
    # data the result page can show even when nothing fit.
    roof_segments = {
        "segments": [
            {
                "segmentIndex": index,
                "pitchDeg": segment.get("pitchDegrees"),
                "azimuthDeg": segment.get("azimuthDegrees"),
                "areaM2": (segment.get("stats") or {}).get("areaMeters2"),
                "groundAreaM2": (segment.get("stats") or {}).get("groundAreaMeters2"),
                "sunshineQuantiles": (segment.get("stats") or {}).get("sunshineQuantiles") or [],
                "planeHeightM": segment.get("planeHeightAtCenterMeters"),
                "polygon": _metric_polygon_to_wgs84_ring(segment_polygons_metric[index], usable_roof.epsg)
                if segment_polygons_metric[index] is not None
                else None,
                # The segment's own area ABOVE (areaM2) is Google's raw,
                # unclipped figure for the whole plane — kept as-is, it's
                # legitimate descriptive metadata. This is the DIFFERENT,
                # real number: how much of THIS segment actually falls
                # inside the customer's own resolved/cropped boundary
                # (zero when segment_polygons_metric[index] is None, i.e.
                # no overlap at all). Exists so a confidence/scoring
                # consumer can weight a segment by what the customer
                # actually selected, never by a Google segment's full
                # extent regardless of overlap — see
                # engine/fitness.py::_aggregate_geometry_confidence().
                "overlapAreaM2": segment_polygons_metric[index].area
                if segment_polygons_metric[index] is not None
                else 0.0,
            }
            for index, segment in enumerate(segments)
        ]
    }

    ranked_indices = sorted(
        range(len(segments)), key=lambda i: _segment_quality_score(segments[i]), reverse=True
    )

    target_watts_remaining = capacity.recommended_kwp * 1000.0
    combined_panels: list[dict] = []
    total_kwp = 0.0
    panel_watts_used: float | None = None
    best_segment_orientation: str | None = None
    best_segment_count = -1
    primary_tilt_deg: float | None = None
    primary_azimuth_deg: float | None = None
    primary_plane_overlap_m2: float | None = None
    total_panel_count = 0
    total_rejected_count = 0
    total_panels_outside_roof = 0
    total_panels_intersecting_obstacles = 0

    for index in ranked_indices:
        if target_watts_remaining <= 0:
            break
        segment = segments[index]
        azimuth, tilt = segment.get("azimuthDegrees"), segment.get("pitchDegrees")
        if azimuth is None or tilt is None:
            continue

        segment_polygon = segment_polygons_metric[index]
        if segment_polygon is None:
            continue

        try:
            full_layout = panel_packing.pack_panels_best_orientation(
                segment_polygon,
                latitude_deg=lat,
                tilt_deg=float(tilt),
                azimuth_deg=float(azimuth),
                **panel_kwargs,
            )
            selected = panel_packing.select_for_target_capacity(
                full_layout, target_watts_remaining / 1000.0
            )
            rings = panel_packing.to_wgs84_rings(selected, usable_roof.epsg)
        except Exception:
            logger.warning(
                "Panel packing failed for segment %d at (%s, %s)", index, lat, lng, exc_info=True
            )
            continue

        if not rings:
            continue

        validation = panel_validation.validate_layout(selected, segment_polygon, exclusions_metric)
        total_panel_count += validation.panel_count
        total_rejected_count += validation.rejected_count
        total_panels_outside_roof += validation.panels_outside_roof
        total_panels_intersecting_obstacles += validation.panels_intersecting_obstacles

        if selected.count > best_segment_count:
            best_segment_count = selected.count
            best_segment_orientation = selected.orientation
            primary_tilt_deg = selected.tilt_deg
            primary_azimuth_deg = selected.azimuth_deg
            # How much of THIS winning plane actually overlaps the
            # customer's crop — used below to caveat the generation
            # estimate when the plane whose pitch/azimuth we're using
            # only partially represents the selected roof, rather than
            # silently presenting it as if it described the whole thing.
            primary_plane_overlap_m2 = segment_polygon.area

        panel_watts_used = selected.panel_watts
        combined_panels.extend(
            {
                "corners": [list(point) for point in ring],
                "segmentIndex": index,
                "azimuthDeg": selected.azimuth_deg,
                "tiltDeg": selected.tilt_deg,
            }
            for ring in rings
        )
        total_kwp += selected.kwp
        target_watts_remaining -= selected.kwp * 1000.0

    # Tilt/azimuth of the plane that actually took the most panels — used
    # by engine/generation.py's PVGIS cross-check instead of a bare
    # latitude/south-facing guess, when a real plane was packed.
    roof_segments["primaryTiltDeg"] = primary_tilt_deg
    roof_segments["primaryAzimuthDeg"] = primary_azimuth_deg
    roof_segments["primaryPlaneOverlapM2"] = primary_plane_overlap_m2

    if not combined_panels:
        return (
            {"status": "no_layout", "reason": "No panels fit the usable roof area", "panels": []},
            roof_segments,
            warning,
        )

    orientation = (best_segment_orientation or "portrait").upper()
    return (
        {
            "status": "ok",
            "orientation": orientation,
            "panelWatts": panel_watts_used,
            "panelCount": len(combined_panels),
            "totalKwp": round(total_kwp, 2),
            "panels": combined_panels,
            "validation": {
                "panelCount": total_panel_count,
                "rejectedCount": total_rejected_count,
                "panelsOutsideRoof": total_panels_outside_roof,
                "panelsIntersectingObstacles": total_panels_intersecting_obstacles,
            },
        },
        roof_segments,
        warning,
    )


def orchestrate_assessment(
    site_id: str,
    owner_org: str | None = None,
    *,
    on_stage: Callable[[str], None] | None = None,
) -> AssessmentResponse:
    """API-01/02. Capacity and fitness are recomputed fresh on every
    call, even when analysis.cache_hit is True — only geometry/vision/
    weather/panorama/ml are reused from Person 3's cache; capacity and
    fitness depend on site-specific things (subsidy tier, jurisdiction)
    the cache key doesn't capture.

    `owner_org` is optional so internal callers without tenant context
    (this module's own tests calling this function directly) don't need
    one — every real HTTP route always passes the caller's real
    owner_org from API-06's current_org dependency. 404, never 403, for
    another tenant's site — same reasoning as routers/sites.py's
    _owned_or_404: confirming the id exists at all is itself a leak.

    `on_stage`, if given, is called with each of ASSESSMENT_STAGES'
    values right before that stage of work starts — Phase 4's real
    backend-driven progress signal for the customer's processing screen
    (see workers/tasks_assessments.py::run_check_assessment_task, which
    forwards these into a Celery task's PROGRESS state). Optional and
    additive: every existing caller (the batch task, this module's own
    tests) passes nothing and behaves exactly as before. Never allowed
    to fail the assessment itself — a reporting sink going down must not
    take the real computation down with it.
    """

    def _stage(name: str) -> None:
        if on_stage is None:
            return
        try:
            on_stage(name)
        except Exception:
            logger.warning("on_stage callback failed for stage %s", name, exc_info=True)

    _stage("resolving_location")
    with session_scope() as session:
        site = sites_repo.get(session, site_id)
        # CON-05's input, read here rather than in a second session. Kept
        # off the domain Site because that contract is frozen Day 0 and
        # only the capacity path below needs it.
        bill_low, bill_high = sites_repo.get_bill_range(session, site_id)
    if site is None or (owner_org is not None and site.owner_org != owner_org):
        raise SiteNotFoundError(f"Site {site_id} not found")

    lng, lat = site.centroid["coordinates"]

    _stage("analyzing_roof_imagery")
    analysis = analysis_cache_repo.get_or_create_analysis(lat, lng, site.site_type, params={})

    # OBS-04/05/07 — classify and (above threshold) auto-apply this
    # site's detected obstacles via the real async task, dispatched
    # against this site's real id (never the cache's site-independent
    # synthetic one — see analysis_cache.py's own note on why that broke
    # auto-apply entirely). Idempotent per site
    # (repositories/sites.py::applied_obstacle_ids), so replaying the
    # same cached detection on every assessment call is safe and cheap
    # once a site has already picked up what applies to it.
    _stage("detecting_obstacles")
    if analysis.vision_refinement and analysis.vision_refinement.obstacles:
        from solarfit.domain.assessment import Obstacle
        from solarfit.workers.celery_app import apply_obstacles_task

        obstacles_payload = [o.model_dump() for o in analysis.vision_refinement.obstacles]
        task_result = apply_obstacles_task.delay(site.id, obstacles_payload).get(
            timeout=config_pack.get_async_task_timeout_s()
        )
        analysis.vision_refinement.obstacles = [Obstacle(**o) for o in task_result["obstacles"]]
        # Pick up any exclusion the apply just persisted before computing
        # usable area below.
        with session_scope() as session:
            site = sites_repo.get(session, site_id)

    # AREA-01..06 — usable_area_m2 isn't a cached field (see
    # analysis_cache.py::_row_to_result's own docstring: it's deliberately
    # left None there so a config-pack coefficient change picks up
    # immediately without needing to invalidate anything). It has to be
    # computed here, fresh, on every call — against the pipeline-resolved
    # boundary (analysis.boundary, which went through VIS/OBS refinement)
    # combined with this site's own persisted exclusions. Previously this
    # read analysis.usable_area_m2 directly, which is always None, so
    # every real (non-mocked) assessment silently computed capacity
    # against a usable area of 0.0.
    #
    # GEO-01 precedence, applied here too. `analysis.boundary` is the
    # cached Solar API geometry — a bounding RECTANGLE around the
    # building, precedence 100. Overwriting the site's own boundary with
    # it unconditionally meant a surveyor could trace the real roof
    # (manual_polygon, 300) or field-measure it (400), have it stored and
    # versioned through SITE-05, and the very next assessment would throw
    # it away and measure Google's box instead.
    #
    # So the traced geometry wins when it STRICTLY outranks the cached
    # one. Equal precedence keeps the old behaviour deliberately: when
    # the site's own boundary is also solar_api, analysis.boundary is
    # the better of the two, because it carries the VIS/OBS refinement
    # the raw stored boundary does not.
    if site.boundary and outranks(site.geometry_source, "solar_api"):
        usable_site = site
        boundary_used = site.geometry_source or "site"
    else:
        usable_site = site.model_copy(update={"boundary": analysis.boundary})
        boundary_used = "solar_api"

    _stage("computing_usable_area")
    usable_roof = compute_usable_roof(usable_site)
    usable_area_m2 = usable_roof.area_m2
    # AREA-01, the roof's raw area before setback/exclusions — real,
    # displayable "total vs usable vs non-usable" figures for the
    # customer report, not derived from a guess.
    total_area_m2 = boundary_area_m2(usable_site)
    logger.info(
        "Site %s: usable area %.1f m2 from the %s boundary", site_id, usable_area_m2, boundary_used
    )

    # CON-05 — the customer's own bill, converted to annual units.
    consumption = estimate_annual_consumption(bill_low, bill_high)

    _stage("sizing_system")
    ceilings, gates = _collect_ceilings_and_gates(
        site, usable_area_m2, consumption.annual_kwh if consumption else None
    )
    capacity = resolver.resolve_capacity(ceilings)

    _stage("placing_panels")
    panel_layout, roof_segments, boundary_warning = _pack_panel_layout(
        usable_roof, capacity, lat, lng, site=usable_site
    )

    _stage("scoring_feasibility")
    # How much of the plane behind primaryTiltDeg/primaryAzimuthDeg above
    # actually overlaps the customer's own selected/cropped area — None
    # when there's no usable area to compare against or no plane was
    # packed at all, in which case estimate_generation_kwh()'s existing
    # "no roof segment data available" path already applies.
    primary_plane_overlap_m2 = (roof_segments or {}).get("primaryPlaneOverlapM2")
    primary_plane_coverage_ratio = (
        primary_plane_overlap_m2 / usable_area_m2
        if primary_plane_overlap_m2 is not None and usable_area_m2
        else None
    )
    generation_estimate = (
        generation.estimate_generation_kwh(
            site,
            capacity.recommended_kwp,
            params={
                "tilt_deg": (roof_segments or {}).get("primaryTiltDeg"),
                "azimuth_deg": (roof_segments or {}).get("primaryAzimuthDeg"),
                "primary_plane_coverage_ratio": primary_plane_coverage_ratio,
            },
        )
        if capacity.recommended_kwp
        else None
    )

    # FIN-01 — indicative cost/subsidy/payback estimate, computed from
    # the same resolved capacity and generation figures above. Never
    # blocks or alters the feasibility verdict — purely additive.
    financial_estimate = financials.estimate_financials(
        site.site_type,
        capacity.recommended_kwp,
        (generation_estimate or {}).get("estimated_kwh_per_year"),
    )

    # CAL-05 — wired in for real (was flagged "not wired into the router
    # yet" when repositories/calibration.py was built).
    calibration_state = calibration.get_calibration_confidence_adjustment(
        site.site_type, site.geometry_source
    )

    fitness_result = fitness.score_fitness(
        site,
        capacity,
        params={
            "gates": gates,
            "generation": generation_estimate,
            "calibration_state": calibration_state,
            # FIT-04 only — real per-plane geometry confidence, area-
            # weighted (see fitness.py::_aggregate_geometry_confidence()).
            # Never read by the FIT-01 score path.
            "roof_segments": roof_segments,
        },
    )

    # ML-01 training-sample capture — wired in for real (was flagged
    # "not called by anything yet" when engine/ml_score.py was built).
    # ML-01 is additive metadata by contract, so nothing here may fail the
    # assessment. The weather lookup in particular is an external call
    # that does go down (Open-Meteo timed out 1 call in 3 while this was
    # written), and a training sample is not worth a customer's verdict.
    weather = None
    if fitness_result.score is not None:
        try:
            weather = weather_provider.fetch_weather(lat, lng)
        except Exception:
            logger.warning("Weather unavailable — skipping ML capture", exc_info=True)
    if fitness_result.score is not None and weather is not None:
        ml_score_engine.record_training_sample(
            site.id,
            analysis.boundary,
            analysis.vision_refinement.model_dump() if analysis.vision_refinement else None,
            weather,
            label_source="fit_score",
            label_value=fitness_result.score,
        )

    _stage("finalizing_result")
    conditions = list(fitness_result.conditions)
    if boundary_warning:
        conditions.append(Condition(code="WRONG_BUILDING_RETURNED", message=boundary_warning))

    return AssessmentResponse(
        site_id=site.id,
        site_type=site.site_type,
        verdict=fitness_result.verdict,
        score=fitness_result.score,
        confidence=fitness_result.confidence,
        binding_constraint=fitness_result.binding_constraint,
        reasons=fitness_result.reasons,
        conditions=conditions,
        limitations=fitness_result.limitations,
        capacity=capacity,
        # The boundary actually measured above (usable_site.boundary) —
        # the site's own mask-derived outline when GEO-01 precedence
        # picked it (geometry_source="solar_api_mask" or better), never
        # unconditionally the cache's bounding-box (analysis.boundary).
        # Previously this always returned analysis.boundary regardless,
        # so a real traced/mask outline would compute the correct usable
        # area but report the cruder rectangle as "the boundary" on the
        # response/persisted row — right area, wrong shape reported.
        boundary=usable_site.boundary or analysis.boundary,
        usable_area_m2=usable_area_m2,
        total_area_m2=total_area_m2,
        score_components=fitness_result.components,
        confidence_components=fitness_result.confidence_components,
        confidence_explanation=fitness_result.confidence_explanation,
        panel_layout=panel_layout,
        roof_segments=roof_segments,
        boundary_warning=boundary_warning,
        vision_refinement=analysis.vision_refinement,
        panorama_url=analysis.panorama.url if analysis.panorama else None,
        ml_suitability_score=analysis.ml_score.score if analysis.ml_score else None,
        ml_model_version=analysis.ml_score.model_version if analysis.ml_score else None,
        cache_hit=analysis.cache_hit,
        reused_from_analysis_id=analysis.reused_from_analysis_id,
        usn=site.usn,
        engine_version=engine_version,
        constraint_pack_version=pack_version(),
        generation=GenerationEstimateOut(**generation_estimate) if generation_estimate else None,
        financial_estimate=FinancialEstimateOut(**financial_estimate) if financial_estimate else None,
    )


# ---------------------------------------------------------------------------
# API-03 — async batch submission with pollable status.
#
# Registered BEFORE POST /{site_id} below: FastAPI/Starlette matches
# routes in registration order, and "/batch" would otherwise be
# captured by the "/{site_id}" path parameter first (site_id="batch"),
# never reaching this route at all.
# ---------------------------------------------------------------------------


class BatchSubmitRequest(BaseModel):
    site_ids: list[str]


class BatchSubmitResponse(BaseModel):
    job_id: str


class BatchStatusResponse(BaseModel):
    job_id: str
    status: str
    results: list[dict] | None = None


@router.post("/batch", response_model=BatchSubmitResponse)
def post_batch_assessment(
    body: BatchSubmitRequest,
    owner_org: Annotated[str, Depends(current_org)],
) -> BatchSubmitResponse:
    from solarfit.workers.tasks_assessments import run_batch_assessment

    # API-06 tenant scoping for a batch: every site_id must belong to the
    # caller before anything is enqueued — otherwise an authenticated
    # caller from one tenant could assess another tenant's sites just by
    # guessing/enumerating ids. 404, not 403, for the same reason
    # _owned_or_404 uses one in sites.py.
    with session_scope() as session:
        for site_id in body.site_ids:
            site = sites_repo.get(session, site_id)
            if site is None or site.owner_org != owner_org:
                raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

    task = run_batch_assessment.delay(body.site_ids)
    return BatchSubmitResponse(job_id=task.id)


@router.get("/batch/{job_id}", response_model=BatchStatusResponse)
def get_batch_assessment_status(
    job_id: str,
    _owner_org: Annotated[str, Depends(current_org)],
) -> BatchStatusResponse:
    """API-06 requires authentication here, but not full per-job tenant
    scoping: a batch job's id isn't recorded against the owner_org that
    submitted it anywhere today, so any authenticated caller who knows
    (or brute-forces) a job_id can currently poll its status. job_id
    itself is an unguessable Celery UUID, which limits the practical
    exposure, but this is a real, narrower gap than full ownership
    checking — flagged here rather than silently treated as closed."""
    async_result = celery_app.AsyncResult(job_id)
    return BatchStatusResponse(
        job_id=job_id,
        status=async_result.status,
        results=async_result.result if async_result.successful() else None,
    )


@router.post("/{site_id}", response_model=AssessmentResponse)
def post_assessment(
    site_id: str,
    owner_org: Annotated[str, Depends(current_org)],
) -> AssessmentResponse:
    try:
        return orchestrate_assessment(site_id, owner_org)
    except SiteNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except GeometryRejected as e:
        # GEO-04: absent Solar API coverage is a recordable outcome, not a
        # server fault. Google covers India building-by-building, so this
        # is the common case here rather than an edge one — a 500 both
        # misreports it as our bug and leaves the caller with nothing
        # actionable. The site still exists; it just needs geometry from a
        # source that outranks solar_api (GEO-02 manual trace, GEO-05
        # import, GEO-06 field measurement).
        raise HTTPException(
            status_code=422,
            detail=(
                f"{e} — this location has no automatic roof data. Trace the "
                "roof boundary manually to continue."
            ),
        ) from e
