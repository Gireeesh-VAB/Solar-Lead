"""Owner: Person 3 (AI Pipeline & Cache).

Implements §9.11 Vision Refinement (VIS-01..06) and the detection half
of §9.16 Obstacle Detection (OBS-01..03) of
Solar_Fitness_Engine_Development_Document_v1.2 — both ride the same
vision-LLM call (OBS-01: never a second crop, never a second call).

Day 2 status: VIS-01..06 are real. Day 3 status: OBS-01..03 are real.

  OBS-01/02  Obstacles ride the same structured-output call as VIS-02.
             A vision-LLM can't reliably emit precise geo-coordinates
             from pixels any more than it can for corrected_boundary
             (see VIS-02's scoping note) — but an obstacle is small and
             well-bounded, so the model instead emits a normalized
             image-fraction bounding box (0..1, origin top-left), and
             this module converts that to a real GeoJSON polygon using
             the crop's own affine transform (crop_to_boundary's
             CroppedImagery.transform) — the same "use the image's own
             geotransform, never approximate" discipline as VIS-01.
  OBS-03     validate_obstacle_polygon() implements GEO-07/08 directly
             here (self-intersection, vertex count, containment in the
             boundary, plausible area) rather than depending on Person
             1's provider-precedence machinery — these are generic
             Shapely/pyproj checks with no dependency on it.

  VIS-01  Crop source imagery to the provider-derived boundary first —
          never send an uncropped tile. Imagery source is the real
          Google Solar API Data Layers `rgbUrl` (a georeferenced
          GeoTIFF), not a plain map screenshot — this is what lets
          crop_to_boundary() use the image's own embedded geotransform
          (via rasterio/GDAL) instead of an approximated pixel mapping,
          and it's the same fetch this file's engine/panorama.py
          neighbour will reuse for VIZ-01's elevation source (dsmUrl).
  VIS-02  Structured-output prompt to the vision-LLM; parse the response.
          Scoping note: the model returns obstruction notes and a
          confidence, not a precise re-drawn boundary polygon — a
          vision-LLM has no reliable way to emit exact geo-coordinates
          from pixels alone. `corrected_boundary` stays None from this
          file until that's solved properly; VIS-03's "advisory
          annotation, never auto-applied" discipline means shipping
          without it today is honest, not a shortcut that breaks a
          promise.
  VIS-03  Store as an annotation; never overwrite the provider geometry.
  VIS-04  Failure/low-confidence -> insufficient_data; never block the
          pipeline on this step. "Low" = below
          config_pack.get_vision_min_confidence().
  VIS-05  Run as a Celery task (workers/) — never in the request path.
  VIS-06  retain_imagery flag defaults False; imagery-licensing review
          is an open legal item, not assumed clear. Enforced here: the
          downloaded GeoTIFF bytes and the cropped PNG both stay
          in-memory only — nothing is written to disk or object
          storage by this module.

Depends on: solarfit.domain.assessment.{VisionRefinement, Obstacle}
(frozen, Day 0/3), solarfit.config.get_settings() for
GOOGLE_SOLAR_API_KEY/OPENAI_API_KEY, solarfit.packs.config_pack for
vision_min_confidence.
"""

import base64
import logging
import time
from dataclasses import dataclass

import httpx
import numpy as np
from affine import Affine
from openai import OpenAI
from pydantic import BaseModel
from pyproj import Geod, Transformer
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from rasterio.mask import mask as rasterio_mask
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform

from solarfit.config import get_settings
from solarfit.domain.assessment import Obstacle, ObstacleType, VisionRefinement
from solarfit.packs.config_pack import (
    get_max_obstacle_area_fraction_of_boundary,
    get_min_obstacle_area_m2,
    get_vision_min_confidence,
)

logger = logging.getLogger(__name__)

RETAIN_IMAGERY = False  # VIS-06 — do not flip without a completed licence review.

_SOLAR_API_DATALAYERS_URL = "https://solar.googleapis.com/v1/dataLayers:get"
_BUILDING_INSIGHTS_URL = "https://solar.googleapis.com/v1/buildingInsights:findClosest"
_VISION_MODEL = "gpt-4o"
_VISION_TIMEOUT_S = 30.0


class TransientError(Exception):
    """Marks a failure as worth retrying (a timeout, or a 5xx) — as
    opposed to a 4xx (bad API key, bad request) or any other failure,
    which is never transient and should propagate immediately."""


def with_retries(fn, *, attempts: int = 3, base_delay_s: float = 0.5, retryable_exceptions=(TransientError,)):
    """A small, dependency-free retry loop with exponential backoff.
    Reused as-is by providers/storage.py — the loop mechanics are
    generic; each caller decides what counts as retryable via
    `retryable_exceptions` and/or by wrapping its own failure modes as
    TransientError before calling this."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except retryable_exceptions as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(base_delay_s * (2**attempt))
    raise last_exc


def _get_with_retries(url: str, *, params: dict | None = None) -> httpx.Response:
    """A GET, retried on timeout or a 5xx — never on a 4xx (e.g. an
    invalid API key isn't going to fix itself on retry #2)."""

    def _do() -> httpx.Response:
        try:
            with httpx.Client(timeout=_VISION_TIMEOUT_S) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                return response
        except httpx.TimeoutException as exc:
            raise TransientError(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                raise TransientError(str(exc)) from exc
            raise

    return with_retries(_do)


def fetch_solar_api_datalayers(lat: float, lng: float, radius_meters: float = 25.0) -> dict:
    """The real imagery source for VIS-01, and later VIZ-01's elevation
    (dsmUrl). One HTTP call to Solar API's Data Layers endpoint; the
    returned URLs still need the API key appended before they can be
    downloaded (see _download_geotiff_bytes)."""
    api_key = get_settings().google_solar_api_key
    params = {
        "location.latitude": lat,
        "location.longitude": lng,
        "radiusMeters": radius_meters,
        "view": "IMAGERY_LAYERS",
        "requiredQuality": "MEDIUM",
        "key": api_key,
    }
    return _get_with_retries(_SOLAR_API_DATALAYERS_URL, params=params).json()


def fetch_building_insights(lat: float, lng: float) -> dict:
    """A buildingInsights:findClosest call — deliberately separate from
    providers/solar_api.py's resolve_via_solar_api() stub (Person 1's
    GEO-04 file, untouched by this function). This exists only to feed
    engine/panorama.py's per-segment shading tint with real
    solarPotential.roofSegmentStats data — never to resolve geometry.
    Some duplicate API traffic against Person 1's eventual GEO-04
    implementation is an accepted, documented tradeoff for not blocking
    on it. Returns {} (not an exception) if the location has no Solar
    API coverage — callers treat that the same as "no shading data"."""
    api_key = get_settings().google_solar_api_key
    params = {
        "location.latitude": lat,
        "location.longitude": lng,
        "requiredQuality": "MEDIUM",
        "key": api_key,
    }
    try:
        return _get_with_retries(_BUILDING_INSIGHTS_URL, params=params).json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:  # no Solar API coverage here
            return {}
        raise


def _download_geotiff_bytes(asset_url: str) -> bytes:
    """Solar API asset URLs (rgbUrl, dsmUrl, ...) require the API key
    appended as a query param to actually fetch the bytes."""
    api_key = get_settings().google_solar_api_key
    separator = "&" if "?" in asset_url else "?"
    return _get_with_retries(f"{asset_url}{separator}key={api_key}").content


def fetch_rgb_imagery(lat: float, lng: float, radius_meters: float = 25.0) -> bytes:
    """Convenience wrapper: Data Layers lookup + rgbUrl download, as
    raw GeoTIFF bytes ready for crop_to_boundary()."""
    layers = fetch_solar_api_datalayers(lat, lng, radius_meters)
    rgb_url = layers.get("rgbUrl")
    if not rgb_url:
        raise ValueError(f"No rgbUrl in Data Layers response for ({lat}, {lng})")
    return _download_geotiff_bytes(rgb_url)


@dataclass(frozen=True)
class CroppedImagery:
    """Everything OBS-01/02's pixel->geo conversion needs, alongside the
    PNG bytes VIS-02 sends to the vision-LLM. `transform` maps a pixel
    *corner* (col, row) in this cropped array to a native-CRS coordinate
    (GDAL convention — rasterio.mask's own out_transform, not a
    hand-rolled approximation)."""

    png_bytes: bytes
    transform: Affine
    crs: CRS | None
    width: int
    height: int


def crop_to_boundary(imagery: bytes, boundary: dict) -> CroppedImagery:
    """VIS-01. `imagery` is a georeferenced GeoTIFF (e.g. from
    fetch_rgb_imagery); `boundary` is GeoJSON in EPSG:4326. Returns the
    crop, cropped to the boundary polygon using the GeoTIFF's own
    embedded geotransform via rasterio/GDAL — never an approximated
    pixel mapping — plus that transform/CRS so OBS-01/02 can convert
    obstacle bounding boxes back to real geo-coordinates later."""
    boundary_geom = shape(boundary)

    with MemoryFile(imagery) as memfile, memfile.open() as dataset:
        geom_for_mask = boundary_geom
        if dataset.crs is not None and dataset.crs.to_epsg() != 4326:
            transformer = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
            geom_for_mask = shapely_transform(transformer.transform, boundary_geom)

        out_image, out_transform = rasterio_mask(dataset, [mapping(geom_for_mask)], crop=True)
        crs = dataset.crs

    bands = out_image[:3] if out_image.shape[0] >= 3 else np.repeat(out_image[:1], 3, axis=0)
    bands = bands.astype("uint8")
    height, width = bands.shape[1], bands.shape[2]

    with MemoryFile() as out_memfile:
        with out_memfile.open(
            driver="PNG",
            height=height,
            width=width,
            count=3,
            dtype="uint8",
        ) as dst:
            dst.write(bands)
        png_bytes = out_memfile.read()

    return CroppedImagery(png_bytes=png_bytes, transform=out_transform, crs=crs, width=width, height=height)


class _ObstacleSchema(BaseModel):
    """One obstacle as the model can actually report it: a type and a
    normalized image-fraction bounding box (0..1, origin top-left of the
    cropped image) — never lat/lng, see OBS-01/02's module-docstring note."""

    type: ObstacleType
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    confidence: float


class _VisionRefinementSchema(BaseModel):
    """The structured-output shape requested from the model. Deliberately
    narrower than the full VisionRefinement domain contract — see VIS-02's
    scoping note above for why corrected_boundary isn't here."""

    obstruction_notes: list[str]
    confidence: float
    obstacles: list[_ObstacleSchema] = []


_GEOD = Geod(ellps="WGS84")


def _bbox_fraction_to_bounding_polygon(item: _ObstacleSchema, cropped: CroppedImagery) -> dict | None:
    """OBS-01/02. Converts a normalized image-fraction bounding box into
    a real GeoJSON Polygon in EPSG:4326, using the crop's own affine
    transform — the same "trust the image's own geotransform" discipline
    as crop_to_boundary(). Returns None for a degenerate box (caller
    drops it, logs a warning)."""
    x_min, x_max = sorted((min(max(item.x_min, 0.0), 1.0), min(max(item.x_max, 0.0), 1.0)))
    y_min, y_max = sorted((min(max(item.y_min, 0.0), 1.0), min(max(item.y_max, 0.0), 1.0)))
    if x_max <= x_min or y_max <= y_min:
        return None

    corners_px = [
        (x_min * cropped.width, y_min * cropped.height),
        (x_max * cropped.width, y_min * cropped.height),
        (x_max * cropped.width, y_max * cropped.height),
        (x_min * cropped.width, y_max * cropped.height),
    ]
    corners_native = [cropped.transform * (col, row) for col, row in corners_px]

    if cropped.crs is not None and cropped.crs.to_epsg() != 4326:
        to_wgs84 = Transformer.from_crs(cropped.crs, "EPSG:4326", always_xy=True)
        corners_lnglat = [to_wgs84.transform(x, y) for x, y in corners_native]
    else:
        corners_lnglat = corners_native

    ring = [list(pt) for pt in corners_lnglat]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def refine_with_vision_model(cropped: CroppedImagery, boundary: dict) -> VisionRefinement:
    """VIS-02..04 + OBS-01/02. One GPT-4 Vision call on the crop from
    crop_to_boundary(). Never raises — failures degrade to an
    insufficient_data VisionRefinement so the pipeline is never blocked
    on this step (VIS-04). obstacles stays [] on any low-confidence or
    failure path — an unreliable overall read shouldn't be trusted for
    obstacle boxes either.

    Any shadow mention in obstruction_notes is qualitative, crop-only
    visual evidence (the prompt deliberately never asks the model to
    attribute a shadow to a surrounding structure it can't see) — it is
    never a substitute for engine/panorama.py's per-segment shading
    tint or the authoritative SHADE-02 shading_score once Person 1/2
    build it."""
    try:
        client = OpenAI(api_key=get_settings().openai_api_key, timeout=_VISION_TIMEOUT_S)
        b64_image = base64.b64encode(cropped.png_bytes).decode("ascii")

        completion = client.chat.completions.parse(
            model=_VISION_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are reviewing a cropped aerial/satellite image of a single "
                        "building rooftop, already cropped to its assessed boundary — "
                        "surrounding buildings, trees, and terrain are NOT visible in this "
                        "image, only the roof itself. Note anything visible that would "
                        "affect solar panel installation (water tanks, HVAC units, "
                        "chimneys, existing panels, vents, antennas, visible shadow "
                        "patches or darkened areas on the roof surface itself, or "
                        "anything else notable). Do not guess at what is casting a shadow "
                        "you can't see the source of — only describe what's visibly on or "
                        "across the roof. Give a confidence (0-1) in how clearly you can "
                        "assess this image — lower it for blurry, dark, or ambiguous crops. "
                        "Also list each distinct physical obstacle you can see on the roof "
                        "itself (water_tank, hvac_unit, chimney, existing_solar_panel, vent, "
                        "antenna, or other) as a normalized bounding box within this image: "
                        "x_min/y_min is the top-left corner, x_max/y_max is the bottom-right "
                        "corner, both in 0..1 fractions of the image's width/height (origin "
                        "top-left) — not pixel counts, not lat/lng. Give each obstacle its "
                        "own confidence (0-1)."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                        }
                    ],
                },
            ],
            response_format=_VisionRefinementSchema,
        )

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            logger.warning("Vision refinement: model returned no parsed content")
            return VisionRefinement(status="insufficient_data")

        min_confidence = get_vision_min_confidence()
        if parsed.confidence < min_confidence:
            logger.info(
                "Vision refinement: confidence %.2f below threshold %.2f", parsed.confidence, min_confidence
            )
            return VisionRefinement(
                obstruction_notes=parsed.obstruction_notes,
                confidence=parsed.confidence,
                status="insufficient_data",
            )

        obstacles = []
        for item in parsed.obstacles:
            bounding_polygon = _bbox_fraction_to_bounding_polygon(item, cropped)
            if bounding_polygon is None:
                logger.warning("Vision refinement: dropping obstacle with degenerate bbox (%s)", item.type)
                continue
            obstacles.append(Obstacle(type=item.type, bounding_polygon=bounding_polygon, confidence=item.confidence))

        return VisionRefinement(
            corrected_boundary=None,  # see VIS-02 scoping note
            obstruction_notes=parsed.obstruction_notes,
            obstacles=obstacles,
            confidence=parsed.confidence,
            status="ok",
        )

    except Exception:
        logger.exception("Vision refinement call failed")
        return VisionRefinement(status="insufficient_data")


def validate_obstacle_polygon(obstacle: Obstacle, boundary: dict) -> bool:
    """OBS-03/GEO-07/08. Rejects invalid/self-intersecting geometry,
    fewer than 3 distinct vertices, an obstacle not contained within the
    boundary, and implausible area (too small to be real, or too large
    relative to the roof itself). Geodesic area via pyproj.Geod, not
    planar EPSG:4326 math — same discipline the codebase enforces
    elsewhere (see test_projection.py / AREA-01)."""
    try:
        poly = shape(obstacle.bounding_polygon)
        boundary_geom = shape(boundary)
    except (TypeError, ValueError, KeyError):
        return False  # malformed GeoJSON

    if poly.geom_type != "Polygon" or poly.is_empty:
        return False
    if not poly.is_valid:  # GEO-07: self-intersection
        return False
    if len(poly.exterior.coords) - 1 < 3:  # GEO-07: fewer than 3 distinct vertices
        return False
    if not boundary_geom.is_valid or boundary_geom.is_empty:
        return False
    if not boundary_geom.covers(poly):  # GEO-08: contained in the boundary (touching an edge is fine)
        return False

    obstacle_area_m2 = abs(_GEOD.geometry_area_perimeter(poly)[0])
    boundary_area_m2 = abs(_GEOD.geometry_area_perimeter(boundary_geom)[0])
    if obstacle_area_m2 < get_min_obstacle_area_m2():  # GEO-07: implausibly small
        return False
    # GEO-07: implausibly large relative to the roof itself
    max_fraction = get_max_obstacle_area_fraction_of_boundary()
    return not (boundary_area_m2 > 0 and obstacle_area_m2 > boundary_area_m2 * max_fraction)
