"""Owner: Person 3 (AI Pipeline & Cache).

Implements §9.12 3D Visualization (VIZ-01..05) of
Solar_Fitness_Engine_Development_Document_v1.2:

  VIZ-01  Mesh from boundary + elevation data. Elevation comes from the
          Solar API Data Layers dsmUrl, fetched via the same
          providers.vision.fetch_solar_api_datalayers()/
          _download_geotiff_bytes() this module's VIS neighbour already
          uses for rgbUrl (VIS-01) — no second imagery path. The mesh
          is additionally tinted with real per-roof-segment shading
          from providers.vision.fetch_building_insights()'s
          solarPotential.roofSegmentStats — each vertex coloured by its
          segment's sunshine relative to the brightest segment on this
          same roof. This is a simpler, panorama-only computation than
          SHADE-02's "relative to the unobstructed regional maximum"
          score — never presented as or substituted for that
          authoritative value. Tinting is best-effort: any failure
          (no key, no coverage, no roofSegmentStats) exports the mesh
          uncoloured rather than blocking generation (VIZ-03).
  VIZ-02  Persist only a reference URL + generation params/version;
          upload the artifact to object storage (providers/storage.py).
  VIZ-03  Insufficient elevation/imagery -> explicit not_generated
          status + reason. Never fabricate a plausible-looking mesh,
          never raise.
  VIZ-04  Regenerate only on boundary-version change or explicit
          refresh. This function does no self-caching — CACHE-02
          already looks up repositories/analysis_cache.py's cache
          *before* calling this at all, so a second call at the same
          rounded lat/long never reaches here. `version` on the
          returned PanoramaResult is a hash of the boundary geometry,
          so a future caller can compare versions explicitly if needed.
  VIZ-05  Run as an async worker task (workers/), chained after VIS
          completes or is skipped — never in the request path.

Rendering decision: no pyrender/Open3D/OpenGL. PanoramaResult.url is
documented only as "a reference URL — the mesh/render artifact lives
in object storage," not specifically a rendered 2D image. This module
exports a .glb mesh (trimesh, pure Python + numpy, no rendering
context needed) for the frontend to render client-side — pyrender's
offscreen path needs a GPU or an OSMesa native build, which is fragile
to unavailable on a plain Windows dev box.

Depends on: solarfit.domain.assessment.PanoramaResult (frozen, Day 0),
solarfit.providers.vision.{fetch_solar_api_datalayers,
_download_geotiff_bytes, fetch_building_insights} (real, Day 2/7),
solarfit.providers.storage (VIZ-02, Day 4).
"""

import hashlib
import json
import logging
from datetime import UTC, datetime

import numpy as np
import trimesh
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.mask import mask as rasterio_mask
from shapely.geometry import mapping, shape
from shapely.geometry.multipoint import MultiPoint
from shapely.ops import transform as shapely_transform
from shapely.ops import triangulate

from solarfit.domain.assessment import PanoramaResult
from solarfit.packs.config_pack import get_panorama_grid_resolution

logger = logging.getLogger(__name__)


def _boundary_version_hash(boundary: dict) -> str:
    """VIZ-04. A stable fingerprint of the boundary geometry."""
    canonical = json.dumps(boundary, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _mesh_from_dsm(dsm_bytes: bytes, boundary_geom) -> tuple[np.ndarray, np.ndarray, list[tuple[float, float]]]:
    """VIZ-01. Crops the DSM to the boundary (same rasterio/GDAL
    geotransform-trusting discipline as providers.vision.crop_to_boundary),
    samples a grid of elevation points, and triangulates them in a local
    metric (not planar-degree) coordinate space centred on the boundary's
    own centroid. Returns (vertices[N,3], faces[M,3], vertex_lnglat) —
    vertex_lnglat is each vertex's real (lng, lat), same order as
    vertices, for _vertex_colors_from_segments()'s shading lookup. All
    three empty if the DSM crop has too few valid points to triangulate."""
    with MemoryFile(dsm_bytes) as memfile, memfile.open() as dataset:
        geom_for_mask = boundary_geom
        dataset_crs = dataset.crs
        if dataset_crs is not None and dataset_crs.to_epsg() != 4326:
            to_native = Transformer.from_crs("EPSG:4326", dataset_crs, always_xy=True)
            geom_for_mask = shapely_transform(to_native.transform, boundary_geom)

        out_image, out_transform = rasterio_mask(dataset, [mapping(geom_for_mask)], crop=True)
        band = out_image[0].astype("float64")
        if dataset.nodata is not None:
            band = np.where(band == dataset.nodata, np.nan, band)

    height, width = band.shape
    if height < 2 or width < 2:
        return np.empty((0, 3)), np.empty((0, 3), dtype=int), []

    grid_resolution = get_panorama_grid_resolution()
    row_step = max(1, height // grid_resolution)
    col_step = max(1, width // grid_resolution)

    centroid = boundary_geom.centroid
    to_local = Transformer.from_crs(
        "EPSG:4326",
        f"+proj=aeqd +lat_0={centroid.y} +lon_0={centroid.x} +datum=WGS84 +units=m +no_defs",
        always_xy=True,
    )

    local_xy: list[tuple[float, float]] = []
    lnglat: list[tuple[float, float]] = []
    heights: list[float] = []
    for row in range(0, height, row_step):
        for col in range(0, width, col_step):
            z = band[row, col]
            if np.isnan(z):
                continue
            # +0.5: transform maps a pixel *corner* (GDAL convention), so
            # this samples the pixel centre, not the corner.
            lng, lat = out_transform * (col + 0.5, row + 0.5)
            local_xy.append(to_local.transform(lng, lat))
            lnglat.append((lng, lat))
            heights.append(float(z))

    if len(local_xy) < 3:
        return np.empty((0, 3)), np.empty((0, 3), dtype=int), []

    index_by_xy = {xy: i for i, xy in enumerate(local_xy)}
    vertices = np.array([[x, y, z] for (x, y), z in zip(local_xy, heights, strict=True)])

    faces = []
    for tri in triangulate(MultiPoint(local_xy)):
        corners = list(tri.exterior.coords)[:3]
        try:
            faces.append([index_by_xy[c] for c in corners])
        except KeyError:
            continue  # a Delaunay triangle vertex that isn't one of our sample points — skip

    return vertices, np.array(faces, dtype=int), lnglat


def _segment_representative_sunshine(segment: dict) -> float | None:
    """The segment's median annual-sunshine-hours quantile — a single
    representative value out of Solar API's typically-11-point quantile
    list, robust to the exact list length."""
    quantiles = segment.get("stats", {}).get("sunshineQuantiles")
    if not quantiles:
        return None
    return float(quantiles[len(quantiles) // 2])


def _segment_contains(segment: dict, lng: float, lat: float) -> bool:
    bbox = segment.get("boundingBox")
    if not bbox:
        return False
    sw, ne = bbox.get("sw", {}), bbox.get("ne", {})
    try:
        return sw["longitude"] <= lng <= ne["longitude"] and sw["latitude"] <= lat <= ne["latitude"]
    except KeyError:
        return False


def _nearest_segment_index(segments: list[dict], candidate_indices: set[int], lng: float, lat: float) -> int | None:
    best_index, best_dist = None, float("inf")
    for i in candidate_indices:
        center = segments[i].get("center")
        if not center or "longitude" not in center or "latitude" not in center:
            continue
        dist = (center["longitude"] - lng) ** 2 + (center["latitude"] - lat) ** 2
        if dist < best_dist:
            best_index, best_dist = i, dist
    return best_index


def _vertex_colors_from_segments(
    vertex_lnglat: list[tuple[float, float]], building_insights: dict
) -> np.ndarray | None:
    """VIZ-01's shading tint. Colours each vertex by its roof segment's
    sunshine relative to the brightest segment on this same roof —
    real Solar API data, not a guess. Returns None (caller exports
    uncoloured) if there's nothing usable to tint with."""
    segments = (building_insights.get("solarPotential") or {}).get("roofSegmentStats") or []
    sunshine_by_index = {
        i: val for i, seg in enumerate(segments) if (val := _segment_representative_sunshine(seg)) is not None
    }
    if not sunshine_by_index:
        return None

    max_sunshine = max(sunshine_by_index.values())
    if max_sunshine <= 0:
        return None

    candidate_indices = set(sunshine_by_index)
    colors = []
    for lng, lat in vertex_lnglat:
        matched = next((i for i in candidate_indices if _segment_contains(segments[i], lng, lat)), None)
        if matched is None:
            matched = _nearest_segment_index(segments, candidate_indices, lng, lat)

        if matched is None:
            colors.append([200, 200, 200, 255])  # neutral grey — no segment matched this vertex
            continue

        relative = sunshine_by_index[matched] / max_sunshine  # 1.0 = this roof's brightest segment
        # Sunny -> warm yellow; shaded -> dark blue-grey.
        colors.append([int(60 + relative * 195), int(60 + relative * 165), int(90 + relative * 40), 255])

    return np.array(colors, dtype="uint8")


def generate_panorama(boundary: dict, weather: dict | None, params: dict | None = None) -> PanoramaResult:
    """VIZ-01..05. Builds a 3D mesh of the roof from `boundary` + Solar
    API DSM elevation, exports it as .glb, and uploads it to object
    storage. Never raises — any failure (missing DSM, too sparse to
    triangulate, storage unconfigured/unreachable) degrades to an
    explicit not_generated result (VIZ-03)."""
    try:
        boundary_geom = shape(boundary)
        centroid = boundary_geom.centroid
        lng, lat = centroid.x, centroid.y

        from solarfit.providers.vision import _download_geotiff_bytes, fetch_solar_api_datalayers

        layers = fetch_solar_api_datalayers(lat, lng)
        dsm_url = layers.get("dsmUrl")
        if not dsm_url:
            return PanoramaResult(status="not_generated", reason="No dsmUrl in Data Layers response")
        dsm_bytes = _download_geotiff_bytes(dsm_url)

        vertices, faces, vertex_lnglat = _mesh_from_dsm(dsm_bytes, boundary_geom)
        if len(faces) == 0:
            return PanoramaResult(status="not_generated", reason="Elevation grid too sparse to triangulate")

        mesh = trimesh.Trimesh(vertices=vertices, faces=faces)

        # Shading tint is best-effort — its own try/except, separate from
        # the outer one, so a shading-fetch failure never turns an
        # otherwise-successful mesh into a not_generated result.
        try:
            from solarfit.providers.vision import fetch_building_insights

            building_insights = fetch_building_insights(lat, lng)
            vertex_colors = _vertex_colors_from_segments(vertex_lnglat, building_insights)
            if vertex_colors is not None:
                mesh.visual.vertex_colors = vertex_colors
        except Exception:
            logger.warning("Shading tint unavailable — exporting mesh uncoloured", exc_info=True)

        glb_bytes = mesh.export(file_type="glb")
        version_hash = _boundary_version_hash(boundary)

        from solarfit.providers.storage import upload_glb

        url = upload_glb(glb_bytes, key=f"panorama/{version_hash}.glb")
        if url is None:
            return PanoramaResult(status="not_generated", reason="Object storage not configured or upload failed")

        return PanoramaResult(url=url, status="ok", generated_at=datetime.now(UTC), version=version_hash)

    except Exception:
        logger.exception("Panorama generation failed")
        return PanoramaResult(status="not_generated", reason="Unexpected failure during panorama generation")
