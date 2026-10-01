"""Owner: Person 1 (Site & Geometry).

Implements GEO-04 (SOLAR_API) AND §9.17 Shading Analysis's extraction
half (SHADE-01) of Solar_Fitness_Engine_Development_Document_v1.2:
Google Geocoding (address -> lat/lng) then Google Solar API
buildingInsights:findClosest; parse into the internal Boundary shape.
Record (never raise on) absent/BASE-tier/sparse responses.

What Building Insights actually gives us
----------------------------------------
The response carries `boundingBox` (a lat/lng rectangle around the
building) and `solarPotential.roofSegmentStats[]` (per-segment pitch,
azimuth, area, sunshine) — it does NOT return a traced roof outline. The
detailed building mask lives in the separate `dataLayers` endpoint as a
raster that would have to be vectorised.

So the boundary produced here is the bounding rectangle, and it is
deliberately marked as such:
  * `imagery_quality` records the tier Google reported.
  * GEO-09 confidence stays low for this source (base 0.60), lower still
    for BASE tier, because a rectangle over an irregular roof
    over-estimates area.
  * `SolarApiResult.roof_area_m2` carries Google's own summed segment
    area, which is a far better area estimate than the rectangle. Callers
    that want accuracy should prefer it; AREA-01 still measures the
    stored polygon, so the two are reconciled by an operator trace or a
    field measurement, both of which outrank this source (GEO-01).

Upgrading to a real outline means adding a `dataLayers` fetch and
vectorising the mask — a second billed call and raster work. Worth doing
only once real usage shows the rectangle is costing conversions.

Failure is data, not an exception
---------------------------------
GEO-04 is explicit: absent coverage, BASE-tier responses and sparse data
are recorded, never raised. In India all three are common, so every one
of them returns a SolarApiResult with `status` set and `boundary=None`.
The caller decides what to do; nothing here crashes an assessment.

Depends on: solarfit.config.get_settings() for GOOGLE_MAPS_API_KEY /
GOOGLE_SOLAR_API_KEY, solarfit.domain.site.ShadingEstimate (frozen,
Day 0), solarfit.providers.base (same track).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal

import httpx
from pyproj import Transformer
from rasterio.features import shapes as rasterio_shapes
from rasterio.io import MemoryFile
from shapely.geometry import Point, box, mapping
from shapely.geometry import shape as shapely_shape
from shapely.ops import transform as shapely_transform

from solarfit.config import get_settings
from solarfit.domain.site import ShadingEstimate, Site
from solarfit.packs import config_pack
from solarfit.providers import base
from solarfit.providers.validation import GeometryRejected

__all__ = [
    "BUILDING_INSIGHTS_URL",
    "GEOCODE_URL",
    "MaskVectorization",
    "RoofPitchAtPoint",
    "SolarApiError",
    "SolarApiProvider",
    "SolarApiResult",
    "bounding_box_to_polygon",
    "compass_direction",
    "extract_roof_polygon_from_mask",
    "extract_shading_estimate",
    "fetch_building_insights",
    "geocode_address",
    "geocode_address_detailed",
    "match_roof_segment",
    "resolve_via_solar_api",
    "roof_pitch_at_point",
]

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
BUILDING_INSIGHTS_URL = "https://solar.googleapis.com/v1/buildingInsights:findClosest"

TIMEOUT_SECONDS = 15.0

ResolutionStatus = Literal[
    "ok",
    "no_coverage",
    "base_tier",
    "sparse",
    "geocode_failed",
    "error",
]


class SolarApiError(RuntimeError):
    """Raised only for conditions the caller genuinely cannot proceed
    past — a missing API key, or a malformed request we built ourselves.
    Absent coverage is NOT one of these (see module docstring)."""


@dataclass
class SolarApiResult:
    """Everything one Building Insights call yields.

    `status` is always meaningful; `boundary` may be None while `status`
    explains why, which is how GEO-04's "record, don't raise" rule is
    expressed in the return type rather than in exception handling.
    """

    status: ResolutionStatus
    boundary: dict | None = None
    centroid: dict | None = None
    shading: ShadingEstimate = field(default_factory=ShadingEstimate)
    imagery_quality: str | None = None
    imagery_date: datetime | None = None
    roof_area_m2: float | None = None
    segment_count: int = 0
    detail: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return self.boundary is not None


# --------------------------------------------------------------------- #
# geometry helpers
# --------------------------------------------------------------------- #


def bounding_box_to_polygon(bbox: dict) -> dict:
    """Google's {sw, ne} rectangle -> a GeoJSON Polygon, counter-clockwise."""
    try:
        sw, ne = bbox["sw"], bbox["ne"]
        west, south = float(sw["longitude"]), float(sw["latitude"])
        east, north = float(ne["longitude"]), float(ne["latitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GeometryRejected(f"boundingBox is malformed: {exc}") from exc

    if east <= west or north <= south:
        raise GeometryRejected("boundingBox has zero or negative extent")

    return {
        "type": "Polygon",
        "coordinates": [
            [[west, south], [east, south], [east, north], [west, north], [west, south]]
        ],
    }


def _select_building_region(regions: list, query_point_metric) -> Any | None:
    """Of every disconnected mask region, which one is the building the
    customer actually pinned?

    The mask covers a query RADIUS, not one building — a dense street can
    put two or three separate rooftops in frame. Never "the biggest blob
    in the image": that silently hands the customer a neighbour's roof
    when their own happens to be smaller. Prefer a region that actually
    contains the pin; a pin sitting a little off the true roof edge is
    ordinary, so fall back to the nearest region within a configured
    margin — beyond that, nothing here is trusted to be the intended
    building.
    """
    containing = [r for r in regions if r.contains(query_point_metric)]
    if containing:
        return max(containing, key=lambda r: r.area)

    nearest = min(regions, key=lambda r: r.distance(query_point_metric))
    max_distance_m = float(config_pack.get_roof_mask_params()["max_pin_distance_m"])
    if nearest.distance(query_point_metric) > max_distance_m:
        return None
    return nearest


@dataclass(frozen=True)
class MaskVectorization:
    """The mask's own read on "is this an unambiguous single building
    near the pin" — the evidence for a customer-facing building-match
    signal that's independent of (and complementary to) routers/
    assessments.py::_building_match_warning()'s Building Insights
    bounding-box check.

    `competing_regions` counts OTHER disconnected mask regions inside
    the query radius, above the noise-size floor, that were NOT the
    selected one — e.g. a dense street with two or three separate
    rooftops in frame. It is populated even when `polygon` ends up None
    (a real region existed, just not one close enough to trust as the
    pin's own building) — a customer is entitled to know other
    buildings were nearby either way. Zero whenever the mask itself
    couldn't be read (empty mask, no region at all)."""

    polygon: dict | None
    competing_regions: int


def _vectorize_building_mask(mask_bytes: bytes, lat: float, lng: float) -> MaskVectorization:
    """The Solar API's own building-mask GeoTIFF (dataLayers `maskUrl`) ->
    a GeoJSON Polygon in EPSG:4326 — a real traced-ish outline, not a
    bounding rectangle.

    The mask is a single-band raster, already in a projected metric CRS
    (verified: EPSG:32644/UTM, 0.1m pixels, values {0, 1} = {not
    building, building}) — rasterio.features.shapes() vectorises it using
    the raster's OWN embedded affine transform, so pixel coordinates never
    get treated as map coordinates (the mistake this function exists to
    avoid). Everything downstream — region selection, simplification —
    stays in that same metric CRS; only the final result is reprojected
    to WGS84, once, at the end.

    `polygon` is None (never raises) whenever there's nothing safe to
    build a polygon from: an empty mask, only noise-sized regions, or no
    region near enough to the query point. The caller falls back to the
    boundingBox rectangle in every one of those cases.
    """
    params = config_pack.get_roof_mask_params()

    with MemoryFile(mask_bytes) as memfile, memfile.open() as dataset:
        band = dataset.read(1)
        is_building = band.astype(bool)
        if not is_building.any():
            return MaskVectorization(polygon=None, competing_regions=0)

        regions = [
            shapely_shape(geom)
            for geom, value in rasterio_shapes(band, mask=is_building, transform=dataset.transform)
            if value and shapely_shape(geom).is_valid
        ]
        min_region_m2 = float(params["min_region_m2"])
        regions = [r for r in regions if r.area >= min_region_m2]
        if not regions:
            return MaskVectorization(polygon=None, competing_regions=0)

        to_metric = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True).transform
        query_point = shapely_transform(to_metric, Point(lng, lat))

        selected = _select_building_region(regions, query_point)
        competing_regions = len(regions) - (1 if selected is not None else 0)
        if selected is None:
            return MaskVectorization(polygon=None, competing_regions=competing_regions)

        # Pixel-stairstep smoothing. preserve_topology=True so a small
        # tolerance cannot collapse the polygon into something invalid.
        simplify_tolerance_m = float(params["simplify_tolerance_m"])
        selected = selected.simplify(simplify_tolerance_m, preserve_topology=True)
        # Heals any self-touching ring simplify can introduce at a
        # near-degenerate vertex — a no-op on an already-valid polygon.
        selected = selected.buffer(0)
        if selected.is_empty or not selected.is_valid or selected.geom_type != "Polygon":
            return MaskVectorization(polygon=None, competing_regions=competing_regions)

        to_wgs84 = Transformer.from_crs(dataset.crs, "EPSG:4326", always_xy=True).transform
        polygon = mapping(shapely_transform(to_wgs84, selected))
        return MaskVectorization(polygon=polygon, competing_regions=competing_regions)


def polygon_centroid(boundary: dict) -> dict | None:
    """GEO-04. A GeoJSON Point centroid computed directly from
    `boundary`'s own ring.

    Exists because a caller that swaps `boundary` from Building
    Insights' rectangle to `extract_roof_polygon_from_mask()`'s
    vectorised polygon (`_select_building_region()` picks the mask
    region nearest the query point independently, and can legitimately
    settle on a different structure than Building Insights did) MUST
    NOT keep displaying/storing whichever centroid was resolved for the
    OTHER boundary — that mismatch is what makes a correctly-drawn crop
    rectangle appear to "dislocate" once the next step recentres its
    map on the stale centroid instead of the polygon actually shown.
    Always recompute from the boundary that is actually being returned.

    A naive planar centroid of raw lat/lng coordinates (no metric
    reprojection) is an adequate approximation at building footprint
    scale (tens of metres) — same tolerance `_select_building_region()`
    itself already works within.
    """
    try:
        centroid = shapely_shape(boundary).centroid
    except (AttributeError, TypeError, ValueError, KeyError):
        return None
    if centroid.is_empty:
        return None
    return {"type": "Point", "coordinates": [centroid.x, centroid.y]}


def centroid_disagreement_m(a: dict | None, b: dict | None) -> float | None:
    """GEO-04. Planar approx distance in metres between two GeoJSON
    Points — good enough at building scale, same tolerance
    `_select_building_region()`'s own metric-CRS 'nearest region' check
    already works within. Returns None when either input is missing
    (nothing to compare — the caller should treat that as "can't rule
    it out", not as a disagreement).

    Exists to let a caller that independently resolved a boundary two
    ways (Building Insights vs. the building mask) check whether they
    actually agree on WHICH building before trusting the mask's answer
    — see resolve_building_at_point()'s and create_site_core()'s use of
    it, both guarding the same mask-swap decision."""
    if not a or not b:
        return None
    try:
        lng1, lat1 = a["coordinates"]
        lng2, lat2 = b["coordinates"]
    except (KeyError, TypeError, ValueError):
        return None
    lat0 = math.radians((lat1 + lat2) / 2)
    m_per_lat = 111_320.0
    m_per_lng = 111_320.0 * math.cos(lat0)
    dx = (lng2 - lng1) * m_per_lng
    dy = (lat2 - lat1) * m_per_lat
    return math.hypot(dx, dy)


def extract_roof_polygon_from_mask(
    lat: float, lng: float, *, radius_meters: float = 25.0
) -> MaskVectorization:
    """GEO-04's real-outline upgrade. Fetches the Solar API's building
    mask (a second, billed Data Layers call, deliberately separate from
    the buildingInsights call resolve_via_solar_api() already makes) and
    vectorises it into a roof polygon — see _vectorize_building_mask()'s
    docstring for how.

    Never raises. A missing mask URL, a download failure, or nothing
    vectorisable all return `MaskVectorization(polygon=None,
    competing_regions=0)` the same way — the caller (routers/sites.py::
    create_site_core) falls back to the boundingBox rectangle whenever
    `polygon` is None, so a mask-extraction failure never blocks site
    creation the way it would if this propagated an exception.
    """
    from solarfit.providers.vision import _download_geotiff_bytes, fetch_solar_api_datalayers

    try:
        layers = fetch_solar_api_datalayers(lat, lng, radius_meters)
        mask_url = layers.get("maskUrl")
        if not mask_url:
            return MaskVectorization(polygon=None, competing_regions=0)
        mask_bytes = _download_geotiff_bytes(mask_url)
        return _vectorize_building_mask(mask_bytes, lat, lng)
    except Exception:
        logger.warning("Roof mask extraction failed at (%s, %s)", lat, lng, exc_info=True)
        return MaskVectorization(polygon=None, competing_regions=0)


def _imagery_date(payload: dict) -> datetime | None:
    d = payload.get("imageryDate") or {}
    try:
        return datetime(int(d["year"]), int(d["month"]), int(d["day"]), tzinfo=UTC)
    except (KeyError, TypeError, ValueError):
        return None


# --------------------------------------------------------------------- #
# SHADE-01
# --------------------------------------------------------------------- #


def extract_shading_estimate(solar_api_response: dict) -> dict:
    """SHADE-01. Pull the shading-relevant fields out of the same
    response resolve_via_solar_api() already fetched — never a second
    call. Returns a dict matching ShadingEstimate's shape.

    `shading_score` is defined as median sunshine across the roof divided
    by the roof's best-lit sunshine: 1.0 means the whole roof is as lit as
    its sunniest spot (unobstructed), lower means part of it sits in
    shadow. That ratio is self-normalising, so it stays comparable
    between Hyderabad and Vizag without a regional baseline — which
    matters because Person 2 multiplies it into a derate (SHADE-03) and
    Person 4 scores it (SHADE-04).

    Missing or zero sunshine data yields source="unavailable" rather than
    a zero score: "we don't know" and "fully shaded" must not collapse
    into the same number.
    """
    potential = solar_api_response.get("solarPotential") or {}
    max_hours = potential.get("maxSunshineHoursPerYear")

    quantiles = ((potential.get("wholeRoofStats") or {}).get("sunshineQuantiles")) or []
    if not quantiles:
        segments = potential.get("roofSegmentStats") or []
        if segments:
            quantiles = (segments[0].get("stats") or {}).get("sunshineQuantiles") or []

    try:
        max_hours = float(max_hours) if max_hours is not None else None
    except (TypeError, ValueError):
        max_hours = None

    if not quantiles or not max_hours or max_hours <= 0:
        return ShadingEstimate(source="unavailable").model_dump()

    try:
        values = [float(q) for q in quantiles]
    except (TypeError, ValueError):
        return ShadingEstimate(source="unavailable").model_dump()

    median = values[len(values) // 2]
    score = max(0.0, min(1.0, median / max_hours))

    return ShadingEstimate(
        sunshine_hours_per_year=max_hours,
        shading_score=round(score, 4),
        source="solar_api",
    ).model_dump()


# --------------------------------------------------------------------- #
# Roof pitch at a point — the "which roof plane is the pin on" lookup for
# StartCheckWizard's Locate step. Same roofSegmentStats[] every other
# consumer in this codebase already treats as real, elevation-derived
# per-plane data (see engine/panorama.py's _snap_to_segment_planes and
# routers/assessments.py's _pack_panel_layout, which build the exact same
# pitchDeg/azimuthDeg/planeHeightM shape from a resolved check's roof) —
# this is the same lookup run standalone, before a check/site exists.
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class RoofPitchAtPoint:
    """One roof segment's real measured plane, matched to a query point.

    Never fabricated: every field here is read straight from Building
    Insights' roofSegmentStats[] for whichever segment the point falls in
    (or, failing that, is nearest to) — see match_roof_segment(). A
    building with no usable segment data has no RoofPitchAtPoint at all
    (the caller gets None), not a zeroed-out one."""

    segment_index: int
    pitch_deg: float
    azimuth_deg: float
    orientation: str
    plane_height_m: float | None
    area_m2: float | None
    ground_area_m2: float | None
    segment_count: int
    matched_by: Literal["contains", "tolerated_contains", "nearest"]
    confidence: Literal["high", "medium", "low"]


def compass_direction(azimuth_deg: float) -> str:
    """Azimuth (0=N, 90=E, 180=S, 270=W, Solar API's own convention — see
    providers/pvgis.py's docstring) -> a 16-point compass label. Mirrors
    frontend/lib/types.ts::compassDirection() so the same number reads the
    same way on either side of the API."""
    points = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]  # fmt: skip
    index = round(((azimuth_deg % 360) + 360) % 360 / 22.5) % 16
    return points[index]


def _segment_contains_point(segment: dict, lat: float, lng: float) -> bool:
    """Same boundingBox-containment test as engine/panorama.py's
    _segment_contains — kept as an independent copy here rather than a
    cross-module import: providers/ is the lower layer engine/ already
    depends on, and this is a small, stable, pure geometry check with no
    reason to ever diverge between the two call sites."""
    bbox = segment.get("boundingBox")
    if not bbox:
        return False
    sw, ne = bbox.get("sw", {}), bbox.get("ne", {})
    try:
        return sw["longitude"] <= lng <= ne["longitude"] and sw["latitude"] <= lat <= ne["latitude"]
    except KeyError:
        return False


def _utm_epsg_for(lng: float, lat: float) -> int:
    """WGS84 UTM zone EPSG for (lng, lat) — a small local copy of
    engine/projection.py::utm_epsg_for's formula, not a cross-module
    import: same layering reason as _segment_contains_point above."""
    zone = min(int((lng + 180.0) // 6.0) + 1, 60)
    return (32600 if lat >= 0 else 32700) + zone


def _distance_to_bbox_m(bbox: dict, lat: float, lng: float) -> float | None:
    """GEO-10. Geodesically real distance (metres) from (lat, lng) to a
    Solar API {sw, ne} boundingBox rectangle — 0.0 whenever the point is
    inside or exactly on the edge. None when the bbox is missing or
    malformed (never guessed at).

    Reprojects into the point's own UTM zone rather than approximating
    metres from raw degree deltas — the tolerance this feeds is only a
    handful of metres, and a flat degree-to-metre conversion drifts
    enough at that scale to matter, especially in longitude."""
    try:
        sw, ne = bbox["sw"], bbox["ne"]
        west, south = float(sw["longitude"]), float(sw["latitude"])
        east, north = float(ne["longitude"]), float(ne["latitude"])
    except (KeyError, TypeError, ValueError):
        return None

    epsg = _utm_epsg_for(lng, lat)
    to_metric = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True).transform
    point_metric = shapely_transform(to_metric, Point(lng, lat))
    rect_metric = shapely_transform(to_metric, box(west, south, east, north))
    return point_metric.distance(rect_metric)


def match_roof_segment(
    segments: list[dict], lat: float, lng: float
) -> tuple[int, Literal["contains", "tolerated_contains", "nearest"]] | None:
    """Which roofSegmentStats[] entry is the query point actually on?

    Three tiers, in order:

    1. "contains" — the point falls inside a segment's own boundingBox
       exactly. The common case.
    2. "tolerated_contains" (GEO-10) — no segment's bbox contains the
       point, but at least one sits within
       config_pack.get_roof_segment_match_tolerance_m() of it. Solar
       API's boundingBox is Google's own measurement, independent of the
       map tiles a customer taps against, and can be off by a few metres
       purely from imagery/geometry registration — this absorbs that
       without pretending it was an exact match. Ties go to the CLOSEST
       qualifying segment (a deterministic, geometrically meaningful
       rule), never to list order.
    3. "nearest" — falls back to the segment with the nearest `center`
       when no segment's bbox is even within tolerance (a pin genuinely
       off the true roof is ordinary and must not read as a confident
       match).

    Returns None only when no segment carries enough geometry to judge
    any tier — never a guess at the first segment in the list."""
    containing = next(
        (i for i, seg in enumerate(segments) if _segment_contains_point(seg, lat, lng)), None
    )
    if containing is not None:
        return containing, "contains"

    tolerance_m = config_pack.get_roof_segment_match_tolerance_m()
    best_tolerant_index, best_tolerant_dist = None, float("inf")
    for i, seg in enumerate(segments):
        bbox = seg.get("boundingBox")
        if not bbox:
            continue
        dist = _distance_to_bbox_m(bbox, lat, lng)
        if dist is not None and dist <= tolerance_m and dist < best_tolerant_dist:
            best_tolerant_index, best_tolerant_dist = i, dist
    if best_tolerant_index is not None:
        return best_tolerant_index, "tolerated_contains"

    best_index, best_dist = None, float("inf")
    for i, seg in enumerate(segments):
        center = seg.get("center")
        if not center or "longitude" not in center or "latitude" not in center:
            continue
        dist = (center["longitude"] - lng) ** 2 + (center["latitude"] - lat) ** 2
        if dist < best_dist:
            best_index, best_dist = i, dist
    return (best_index, "nearest") if best_index is not None else None


def roof_pitch_at_point(
    raw_building_insights: dict, lat: float, lng: float, *, imagery_quality: str | None
) -> RoofPitchAtPoint | None:
    """The real, measured pitch/azimuth/height of whichever roof plane
    (lat, lng) lands on — None when the response carries no segment with
    both a pitch and an azimuth to report, so a caller never has a
    fabricated value to accidentally trust.

    Confidence is about how much to trust the MATCH, not the segment data
    itself (Solar API's own numbers are taken as given, same as every
    other consumer here) — "high" only when the point fell EXACTLY inside
    the matched segment's own boundingBox on non-BASE imagery. GEO-10's
    "tolerated_contains" (within config_pack.get_
    roof_segment_match_tolerance_m() of the bbox, but not strictly inside
    it) is never "high" — it wasn't literally the reported geometry — but
    it's also never automatically "low": the offset was small enough to
    validate, so it lands at "medium" regardless of imagery tier, exactly
    like an exact match on BASE imagery. A genuine "nearest"-only match
    stays "medium" on non-BASE imagery and only drops to "low" when
    BOTH the match is untrustworthy AND the imagery itself is BASE
    tier — unchanged from before this tier was added."""
    segments = (raw_building_insights.get("solarPotential") or {}).get("roofSegmentStats") or []
    if not segments:
        return None

    match = match_roof_segment(segments, lat, lng)
    if match is None:
        return None
    index, matched_by = match

    segment = segments[index]
    pitch, azimuth = segment.get("pitchDegrees"), segment.get("azimuthDegrees")
    if pitch is None or azimuth is None:
        return None

    high_tier = imagery_quality not in (None, "BASE")
    if matched_by == "contains" and high_tier:
        confidence: Literal["high", "medium", "low"] = "high"
    elif matched_by == "nearest" and not high_tier:
        confidence = "low"
    else:
        confidence = "medium"

    stats = segment.get("stats") or {}
    return RoofPitchAtPoint(
        segment_index=index,
        pitch_deg=float(pitch),
        azimuth_deg=float(azimuth),
        orientation=compass_direction(float(azimuth)),
        plane_height_m=segment.get("planeHeightAtCenterMeters"),
        area_m2=stats.get("areaMeters2"),
        ground_area_m2=stats.get("groundAreaMeters2"),
        segment_count=len(segments),
        matched_by=matched_by,
        confidence=confidence,
    )


# --------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------- #


def _key(kind: str = "solar") -> str:
    settings = get_settings()
    value = settings.google_solar_api_key if kind == "solar" else settings.google_maps_api_key
    # One key with both APIs enabled is the normal setup, so fall back
    # rather than making the operator paste the same value twice.
    value = value or settings.google_maps_api_key or settings.google_solar_api_key
    if not value:
        raise SolarApiError(
            "no Google API key configured — set GOOGLE_MAPS_API_KEY (and/or "
            "GOOGLE_SOLAR_API_KEY) in backend/.env"
        )
    return value


def geocode_address(address: str, *, client: httpx.Client | None = None) -> dict | None:
    """Address -> GeoJSON Point, or None when Google cannot place it.

    Returns None rather than raising for ZERO_RESULTS: an address the
    geocoder does not recognise is ordinary user input, not a fault.

    Kept as a pure GeoJSON accessor — callers that only want geometry get
    exactly that, with no extra keys polluting the object. Use
    geocode_address_detailed() when Google's own formatted address is
    wanted too (the customer-facing search echoes it back so the user can
    see WHICH place was matched).
    """
    found = geocode_address_detailed(address, client=client)
    return found[0] if found else None


def geocode_address_detailed(
    address: str, *, client: httpx.Client | None = None
) -> tuple[dict, str | None] | None:
    """As geocode_address(), but also returns Google's formatted_address.

    Same single HTTP call and the same error discipline; the only
    difference is that the display string survives instead of being
    discarded.
    """
    params = {"address": address, "key": _key("maps")}
    owns_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        response = client.get(GEOCODE_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    finally:
        if owns_client:
            client.close()

    status = payload.get("status")
    if status == "ZERO_RESULTS":
        return None
    # Order matters: REQUEST_DENIED / OVER_QUERY_LIMIT also come back with
    # no results, and returning None for those would report a broken key
    # as "we couldn't find that address" — sending everyone hunting for a
    # geocoding problem that is really a billing one.
    if status != "OK":
        raise SolarApiError(
            f"geocoding failed: {status} {payload.get('error_message', '')}".strip()
        )
    if not payload.get("results"):
        return None

    best = payload["results"][0]
    location = best["geometry"]["location"]
    point = {"type": "Point", "coordinates": [float(location["lng"]), float(location["lat"])]}
    return point, best.get("formatted_address")


def reverse_geocode(lat: float, lng: float, *, client: httpx.Client | None = None) -> str | None:
    """Coordinates -> Google's formatted_address, or None when nothing
    covers that point.

    Same endpoint as geocode_address_detailed(), just `latlng=` instead of
    `address=` — Google's Geocoding API handles both directions. Used
    after "use my current location" / a manual pin drop, so the address
    text shown to the customer always names the point the pin is actually
    on, not whatever they last typed."""
    params = {"latlng": f"{lat},{lng}", "key": _key("maps")}
    owns_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        response = client.get(GEOCODE_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    finally:
        if owns_client:
            client.close()

    status = payload.get("status")
    if status == "ZERO_RESULTS":
        return None
    if status != "OK":
        raise SolarApiError(
            f"reverse geocoding failed: {status} {payload.get('error_message', '')}".strip()
        )
    results = payload.get("results")
    if not results:
        return None
    return results[0].get("formatted_address")


def fetch_building_insights(
    lat: float,
    lng: float,
    *,
    required_quality: str = "BASE",
    client: httpx.Client | None = None,
) -> tuple[int, dict]:
    """Raw Building Insights call. Returns (status_code, payload).

    404 is returned as data, not raised — it simply means no building is
    covered at that point, which GEO-04 treats as a recordable outcome.
    """
    params = {
        "location.latitude": lat,
        "location.longitude": lng,
        "requiredQuality": required_quality,
        "key": _key("solar"),
    }
    owns_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        response = client.get(BUILDING_INSIGHTS_URL, params=params)
    finally:
        if owns_client:
            client.close()

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    return response.status_code, payload


# --------------------------------------------------------------------- #
# GEO-04
# --------------------------------------------------------------------- #


def resolve_from_payload(payload: dict) -> SolarApiResult:
    """Turn a Building Insights payload into a SolarApiResult.

    Split out from the HTTP call so the parsing — where all the real
    decisions live — is testable without a network or a key.
    """
    potential = payload.get("solarPotential") or {}
    segments = potential.get("roofSegmentStats") or []
    quality = payload.get("imageryQuality")

    centroid = None
    centre = payload.get("center") or {}
    if "latitude" in centre and "longitude" in centre:
        centroid = {
            "type": "Point",
            "coordinates": [float(centre["longitude"]), float(centre["latitude"])],
        }

    roof_area = (potential.get("wholeRoofStats") or {}).get("areaMeters2")
    try:
        roof_area = float(roof_area) if roof_area is not None else None
    except (TypeError, ValueError):
        roof_area = None

    shading = ShadingEstimate(**extract_shading_estimate(payload))
    imagery_date = _imagery_date(payload)

    bbox = payload.get("boundingBox")
    if not bbox:
        return SolarApiResult(
            status="sparse",
            centroid=centroid,
            shading=shading,
            imagery_quality=quality,
            imagery_date=imagery_date,
            roof_area_m2=roof_area,
            segment_count=len(segments),
            detail="response carried no boundingBox — nothing to derive a boundary from",
            raw=payload,
        )

    try:
        boundary = bounding_box_to_polygon(bbox)
    except GeometryRejected as exc:
        return SolarApiResult(
            status="sparse",
            centroid=centroid,
            shading=shading,
            imagery_quality=quality,
            imagery_date=imagery_date,
            roof_area_m2=roof_area,
            segment_count=len(segments),
            detail=str(exc),
            raw=payload,
        )

    # BASE tier is usable but noticeably worse — recorded so GEO-09 can
    # mark the confidence down rather than treating it as a HIGH-quality
    # result (GEO-04: "handle ... BASE-tier ... without failure").
    status: ResolutionStatus = "base_tier" if quality == "BASE" else "ok"
    detail = None
    if not segments:
        status = "sparse" if status == "ok" else status
        detail = "building found but no roof segments returned"

    return SolarApiResult(
        status=status,
        boundary=boundary,
        centroid=centroid,
        shading=shading,
        imagery_quality=quality,
        imagery_date=imagery_date,
        roof_area_m2=roof_area,
        segment_count=len(segments),
        detail=detail,
        raw=payload,
    )


def resolve_for_location(
    lat: float,
    lng: float,
    *,
    required_quality: str = "BASE",
    client: httpx.Client | None = None,
) -> SolarApiResult:
    """GEO-04 for a known lat/lng."""
    try:
        code, payload = fetch_building_insights(
            lat, lng, required_quality=required_quality, client=client
        )
    except httpx.HTTPError as exc:
        # A network failure is not a coverage answer; record it as such
        # so a retry is distinguishable from a genuine no-coverage.
        return SolarApiResult(status="error", detail=f"Solar API request failed: {exc}")

    if code == 404:
        return SolarApiResult(
            status="no_coverage",
            detail="no building covered at this location",
            raw=payload,
        )
    if code != 200:
        message = (payload.get("error") or {}).get("message") or f"HTTP {code}"
        return SolarApiResult(status="error", detail=f"Solar API error: {message}", raw=payload)

    return resolve_from_payload(payload)


def resolve_for_address(
    address: str, *, required_quality: str = "BASE", client: httpx.Client | None = None
) -> SolarApiResult:
    """GEO-04 end to end: address -> geocode -> Building Insights."""
    point = geocode_address(address, client=client)
    if point is None:
        return SolarApiResult(status="geocode_failed", detail=f"could not geocode {address!r}")

    lng, lat = point["coordinates"]
    result = resolve_for_location(lat, lng, required_quality=required_quality, client=client)
    if result.centroid is None:
        result.centroid = point
    return result


def resolve_via_solar_api(site: Site, params: dict) -> dict:
    """GEO-04, provider entry point. Returns a GeoJSON Polygon.

    Raises GeometryRejected when no boundary could be resolved — at the
    provider boundary the caller asked for geometry and there is none.
    Callers that want the richer outcome (status, shading, imagery tier)
    should call resolve_for_location()/resolve_for_address() directly,
    which is what routers/sites.py does.
    """
    client = params.get("client")
    quality = params.get("required_quality", "BASE")

    if params.get("address"):
        result = resolve_for_address(params["address"], required_quality=quality, client=client)
    else:
        centroid = site.centroid or {}
        coords = centroid.get("coordinates")
        if not coords:
            raise GeometryRejected("solar_api provider needs a site centroid or params['address']")
        result = resolve_for_location(
            float(coords[1]), float(coords[0]), required_quality=quality, client=client
        )

    if not result.usable:
        raise GeometryRejected(
            f"Solar API could not resolve a boundary ({result.status}): "
            f"{result.detail or 'no detail'}"
        )
    return result.boundary  # type: ignore[return-value]


class SolarApiProvider:
    """GEO-04. Boundary derived from Google Solar API building insights."""

    id = "solar_api"
    applies_to: ClassVar[list[str]] = []  # every rooftop type

    def resolve(self, site: Site, params: dict) -> dict:
        return resolve_via_solar_api(site, params)


base.register(SolarApiProvider())
