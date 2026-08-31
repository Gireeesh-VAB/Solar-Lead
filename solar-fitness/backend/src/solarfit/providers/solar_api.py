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

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal

import httpx

from solarfit.config import get_settings
from solarfit.domain.site import ShadingEstimate, Site
from solarfit.providers import base
from solarfit.providers.validation import GeometryRejected

__all__ = [
    "BUILDING_INSIGHTS_URL",
    "GEOCODE_URL",
    "SolarApiError",
    "SolarApiProvider",
    "SolarApiResult",
    "bounding_box_to_polygon",
    "extract_shading_estimate",
    "fetch_building_insights",
    "geocode_address",
    "resolve_via_solar_api",
]

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
        raise SolarApiError(f"geocoding failed: {status} {payload.get('error_message', '')}".strip())
    if not payload.get("results"):
        return None

    location = payload["results"][0]["geometry"]["location"]
    return {"type": "Point", "coordinates": [float(location["lng"]), float(location["lat"])]}


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
