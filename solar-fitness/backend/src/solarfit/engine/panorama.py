"""Owner: Person 3 (AI Pipeline & Cache).

Implements §9.12 3D Visualization (VIZ-01..05) of
Solar_Fitness_Engine_Development_Document_v1.2:

  VIZ-01  A 3D building assembled from real measured data — never a
          stand-in model. Four parts, each from a real source:

            Roof    Solar API Data Layers dsmUrl elevation, cropped to
                    the boundary and triangulated. Tinted per roof
                    segment with real sunshine data (see below).
            Walls   The roof perimeter extruded down to a ground level
                    estimated from the DSM itself (_ground_elevation).
            Ground  A flat plane at that same level. Deliberately
                    featureless — BASE-tier DSM around the footprint
                    does not support modelled terrain, and inventing
                    some would misrepresent the source.
            Panels  solarPotential.solarPanels[] — Google's real
                    per-panel layout, each panel at its own centre and
                    orientation, sized by the response's own
                    panelHeight/WidthMeters, tilted by its segment's
                    pitch/azimuth.

          Elevation and imagery come from the same
          providers.vision.fetch_solar_api_datalayers()/
          _download_geotiff_bytes() pair the VIS neighbour already uses
          for rgbUrl (VIS-01) — no second imagery path. Panels and
          shading both come from one
          providers.vision.fetch_building_insights() call.

          The shading tint colours each vertex by its segment's sunshine
          relative to the brightest segment on this same roof. That is a
          simpler, panorama-only computation than SHADE-02's "relative
          to the unobstructed regional maximum" score — never presented
          as or substituted for that authoritative value.

          IMPORTANT — the panel layout is GOOGLE'S, not P2's. P2 derives
          capacity as usable_area_m2 x a density constant and produces
          no panel positions, counts or dimensions whatsoever, so there
          is nothing of P2's to place. The two figures disagree
          substantially (measured 2026-09-02 at a Hyderabad rooftop: P2
          92.5 kWp / 231 implied panels against Google's 6 panels /
          2.4 kWp). Any UI showing both must label which is which rather
          than implying the 3D view depicts P2's number.

  VIZ-02  Persist only a reference URL + generation params/version;
          upload the artifact to object storage (providers/storage.py).
  VIZ-03  Insufficient elevation/imagery -> explicit not_generated
          status + reason. Never fabricate a plausible-looking mesh,
          never raise. Degradation is graded: no DSM at all is
          not_generated, while a missing ground estimate or a missing
          panel layout still exports the parts that are real.
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

The .glb is a glTF scene of four separately-named meshes (Roof, Walls,
Ground, SolarPanels) so the viewer can toggle layers without a second
download or any client-side reconstruction.

Depends on: solarfit.domain.assessment.PanoramaResult (frozen, Day 0),
solarfit.providers.vision.{fetch_solar_api_datalayers,
_download_geotiff_bytes, fetch_building_insights} (real, Day 2/7),
solarfit.providers.storage (VIZ-02, Day 4).
"""

import contextlib
import hashlib
import json
import logging
import math
from datetime import UTC, datetime

import numpy as np
import trimesh
import trimesh.creation
import trimesh.transformations
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.io import MemoryFile
from rasterio.mask import mask as rasterio_mask
from shapely import contains_xy as shapely_contains_xy
from shapely.geometry import mapping, shape
from shapely.geometry.multipoint import MultiPoint
from shapely.ops import transform as shapely_transform
from shapely.ops import triangulate

from solarfit.domain.assessment import PanoramaResult
from solarfit.packs.config_pack import get_panorama_build_params, get_panorama_grid_resolution

logger = logging.getLogger(__name__)

# Perimeter sampling for wall extrusion, metres. Fine enough that a wall
# follows an undulating roof edge; coarse enough to stay cheap.
_WALL_SEGMENT_M = 1.5

# Below this many usable pixels outside the roof, a ground percentile is
# noise rather than an estimate.
_MIN_GROUND_SAMPLES = 20

# Corner tolerance when reducing the roof hull to a building footprint.
_OUTLINE_SIMPLIFY_M = 1.0

_WALL_COLOR = (206, 201, 193, 255)  # warm off-white, reads as masonry
_GROUND_COLOR = (176, 182, 168, 255)  # muted sage, recedes behind the building
# A real module is a dark laminate in a light aluminium frame. Rendering
# both is what separates an array of individual panels from one navy slab.
_PANEL_GLASS_COLOR = (28, 45, 100, 255)
_PANEL_FRAME_COLOR = (176, 181, 190, 255)

# The laminate slab's own depth, and how far its top clears the frame's.
# Both are rendering constants rather than pack config: they exist to
# make the module legible and to keep the two surfaces off each other in
# the depth buffer, not to describe any real hardware.
_PANEL_GLASS_DEPTH_M = 0.010
_PANEL_GLASS_PROUD_M = 0.003

# Triangles per rendered module: a 12-triangle frame box plus a
# 12-triangle glass box. Tests count panels with this rather than a
# hardcoded 12, which silently broke when the frame was added.
FACES_PER_PANEL = 24
VERTICES_PER_PANEL = 16


def _gltf_y_up() -> np.ndarray:
    """glTF is a Y-up format; this module builds everything Z-up, because
    Z is elevation and every other geometry call here works in that frame.

    trimesh exports the scene graph as given and does NOT insert the
    conversion, so without this the .glb declares Z-up geometry to a Y-up
    consumer: three.js renders the building lying on its back, with the
    ground plane standing vertically through it. Confirmed in a real
    browser — every server-side check passed because they all read the raw
    Z-up vertices, which were correct all along.

    Applied as a NODE transform rather than baked into the vertices, so
    the meshes stay Z-up for anything reading them directly (the tests,
    _nearest_roof_z) while the exported file is upright and spec-correct
    in any viewer.
    """
    return trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0])


def _boundary_version_hash(boundary: dict) -> str:
    """VIZ-04. A stable fingerprint of the boundary geometry."""
    canonical = json.dumps(boundary, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _local_transformer(boundary_geom) -> Transformer:
    """WGS84 -> a local metric frame centred on the boundary's own
    centroid: x east, y north, both in metres. Every part of the model is
    built in this one frame, which is what lets panels placed from
    lat/lng land on a roof built from raster pixels."""
    centroid = boundary_geom.centroid
    return Transformer.from_crs(
        "EPSG:4326",
        f"+proj=aeqd +lat_0={centroid.y} +lon_0={centroid.x} +datum=WGS84 +units=m +no_defs",
        always_xy=True,
    )


def _keep_roof_samples(
    local_xy: list[tuple[float, float]],
    lnglat: list[tuple[float, float]],
    heights: list[float],
    ground_z: float | None = None,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]], list[float]]:
    """Drops sampled pixels that are not roof.

    GEO-04 resolves a 4-vertex BOUNDING BOX, not a traced roof outline
    (providers/solar_api.py says so in its own docstring), so the DSM crop
    reliably catches ground, courtyard and street beside the building.
    Triangulating those together with the roof stretches faces across the
    full drop — measured 21 m at a real Hyderabad site, ground at 576 m
    against a roof at 596 m — which renders as a fan rather than a
    building, and drops panels onto the ground pixels where they vanish
    inside it.

    The roof is the high cluster. Anything more than max_roof_step_m below
    the upper quartile is a mis-cropped surface and goes. The quartile
    rather than the median is deliberate: it stays anchored to the roof
    even when the box catches so much ground that ground pixels are the
    majority.
    """
    z = np.asarray(heights)
    params = get_panorama_build_params()
    if ground_z is not None:
        # Anchored on the measured ground, so EVERY roof level survives —
        # a lower wing at 11 m and a main roof at 17 m both stay.
        # Anchoring on the roof's own upper quartile instead cut the lower
        # wing away, and Google still placed panels on it: 11 of 57 panels
        # ended up floating up to 3.4 m past the roof edge.
        cutoff = ground_z + params["min_building_height_m"]
    else:
        # No ground estimate — fall back to the quantile band.
        cutoff = float(np.percentile(z, 75)) - params["max_roof_step_m"]
    keep = z >= cutoff
    dropped = int((~keep).sum())
    if dropped:
        logger.info(
            "Roof extraction: dropped %d of %d samples below %.1f m as non-roof",
            dropped,
            len(z),
            cutoff,
        )
    return (
        [xy for xy, k in zip(local_xy, keep, strict=True) if k],
        [ll for ll, k in zip(lnglat, keep, strict=True) if k],
        [h for h, k in zip(heights, keep, strict=True) if k],
    )


def _mesh_from_dsm(
    dsm_bytes: bytes, boundary_geom, ground_z: float | None = None
) -> tuple[np.ndarray, np.ndarray, list[tuple[float, float]]]:
    """VIZ-01. Crops the DSM to the boundary (same rasterio/GDAL
    geotransform-trusting discipline as providers.vision.crop_to_boundary),
    samples a grid of elevation points, and triangulates them in a local
    metric (not planar-degree) coordinate space centred on the boundary's
    own centroid. Returns (vertices[N,3], faces[M,3], vertex_lnglat) —
    vertex_lnglat is each vertex's real (lng, lat), same order as
    vertices, for _vertex_colors_from_segments()'s shading lookup. All
    three empty if the DSM crop has too few valid points to triangulate.

    Z is absolute elevation in metres above the DSM's datum; the caller
    re-bases it against ground level."""
    with MemoryFile(dsm_bytes) as memfile, memfile.open() as dataset:
        geom_for_mask = boundary_geom
        dataset_crs = dataset.crs
        if dataset_crs is not None and dataset_crs.to_epsg() != 4326:
            to_native = Transformer.from_crs("EPSG:4326", dataset_crs, always_xy=True)
            geom_for_mask = shapely_transform(to_native.transform, boundary_geom)

        # filled=False returns a masked array, so pixels outside the roof
        # polygon are *masked* rather than replaced with a fill value.
        # These DSM rasters declare no nodata (dataset.nodata is None), so
        # the previous `if dataset.nodata is not None` guard never fired
        # and rasterio's default fill of 0 came through as real elevation:
        # 857 zeroes sitting beside genuine heights of ~518 m, giving the
        # mesh a 520-metre cliff around the roof.
        out_image, out_transform = rasterio_mask(
            dataset, [mapping(geom_for_mask)], crop=True, filled=False
        )
        band = np.ma.filled(out_image[0].astype("float64"), np.nan)
        if dataset.nodata is not None:
            band = np.where(band == dataset.nodata, np.nan, band)

    height, width = band.shape
    if height < 2 or width < 2:
        return np.empty((0, 3)), np.empty((0, 3), dtype=int), []

    # out_transform maps pixels to the DATASET's CRS, which is the DSM's
    # own projection (EPSG:32644 for Hyderabad), not lat/lng — the mask
    # above deliberately reprojected the boundary into it. Every sampled
    # pixel therefore comes out as UTM metres and has to come back to
    # degrees before anything treats it as a coordinate. Without this the
    # metres were fed straight into a from_crs("EPSG:4326", ...)
    # transformer, every point became inf, all 702 samples collapsed onto
    # one, and Delaunay raised LocateFailureException — which
    # generate_panorama()'s catch-all then turned into a silent
    # not_generated. The `lng, lat` variable naming below is what hid it.
    native_to_wgs84 = (
        Transformer.from_crs(dataset_crs, "EPSG:4326", always_xy=True).transform
        if dataset_crs is not None and dataset_crs.to_epsg() != 4326
        else None
    )

    grid_resolution = get_panorama_grid_resolution()
    row_step = max(1, height // grid_resolution)
    col_step = max(1, width // grid_resolution)

    to_local = _local_transformer(boundary_geom)

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
            native_x, native_y = out_transform * (col + 0.5, row + 0.5)
            lng, lat = (
                native_to_wgs84(native_x, native_y) if native_to_wgs84 else (native_x, native_y)
            )
            local_xy.append(to_local.transform(lng, lat))
            lnglat.append((lng, lat))
            heights.append(float(z))

    if len(local_xy) < 3:
        return np.empty((0, 3)), np.empty((0, 3), dtype=int), []

    local_xy, lnglat, heights = _keep_roof_samples(local_xy, lnglat, heights, ground_z)
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


def _nearest_segment_index(
    segments: list[dict], candidate_indices: set[int], lng: float, lat: float
) -> int | None:
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
        i: val
        for i, seg in enumerate(segments)
        if (val := _segment_representative_sunshine(seg)) is not None
    }
    if not sunshine_by_index:
        return None

    max_sunshine = max(sunshine_by_index.values())
    if max_sunshine <= 0:
        return None

    candidate_indices = set(sunshine_by_index)
    colors = []
    for lng, lat in vertex_lnglat:
        matched = next(
            (i for i in candidate_indices if _segment_contains(segments[i], lng, lat)), None
        )
        if matched is None:
            matched = _nearest_segment_index(segments, candidate_indices, lng, lat)

        if matched is None:
            colors.append([200, 200, 200, 255])  # neutral grey — no segment matched this vertex
            continue

        relative = sunshine_by_index[matched] / max_sunshine  # 1.0 = this roof's brightest segment
        # Sunny -> warm yellow; shaded -> dark blue-grey.
        colors.append(
            [int(60 + relative * 195), int(60 + relative * 165), int(90 + relative * 40), 255]
        )

    return np.array(colors, dtype="uint8")


def _nearest_roof_z(roof_vertices: np.ndarray, x: float, y: float, k: int = 5) -> float:
    """Elevation of the roof surface at (x, y), as the mean of the k
    nearest sampled roof vertices. Averaging rather than taking the single
    nearest keeps one noisy DSM pixel from floating a panel above the roof
    or burying it inside."""
    d2 = (roof_vertices[:, 0] - x) ** 2 + (roof_vertices[:, 1] - y) ** 2
    count = min(k, len(d2))
    nearest = np.argpartition(d2, count - 1)[:count] if count < len(d2) else np.arange(len(d2))
    return float(roof_vertices[nearest, 2].mean())


def _ground_elevation(
    dsm_bytes: bytes, boundary_geom, to_local: Transformer, params: dict[str, float]
) -> float | None:
    """VIZ-01's wall half. Estimates ground level from the DSM itself.

    The roof crop is masked to the boundary, so it holds no ground pixels
    at all — this re-crops to a buffered boundary and reads only the
    pixels OUTSIDE the roof polygon. A low percentile of those is taken as
    ground: neighbouring buildings and trees sit above true ground and
    would drag a mean upward, while the raw minimum would chase a single
    noisy pixel.

    Returns None when the DSM cannot support an estimate — the caller
    falls back to a configured height rather than inventing terrain.
    """
    # Buffer in the local metric frame, never in degrees — a degree buffer
    # is the §17 planar-measurement mistake wearing a different hat.
    from_local = Transformer.from_crs(to_local.target_crs, "EPSG:4326", always_xy=True)
    local_boundary = shapely_transform(to_local.transform, boundary_geom)
    buffered = shapely_transform(
        from_local.transform, local_boundary.buffer(params["ground_search_buffer_m"])
    )

    try:
        with MemoryFile(dsm_bytes) as memfile, memfile.open() as dataset:
            search_geom, roof_geom = buffered, boundary_geom
            if dataset.crs is not None and dataset.crs.to_epsg() != 4326:
                to_native = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
                search_geom = shapely_transform(to_native.transform, buffered)
                roof_geom = shapely_transform(to_native.transform, boundary_geom)

            out_image, out_transform = rasterio_mask(
                dataset, [mapping(search_geom)], crop=True, filled=False
            )
            band = np.ma.filled(out_image[0].astype("float64"), np.nan)
            if dataset.nodata is not None:
                band = np.where(band == dataset.nodata, np.nan, band)

            # invert=False -> True OUTSIDE the roof polygon, i.e. candidate ground.
            outside_roof = geometry_mask(
                [mapping(roof_geom)],
                out_shape=band.shape,
                transform=out_transform,
                invert=False,
            )
    except (ValueError, IndexError):
        logger.info("Ground estimate: DSM does not usably cover the buffered boundary")
        return None

    candidates = band[outside_roof & ~np.isnan(band)]
    if candidates.size < _MIN_GROUND_SAMPLES:
        logger.info("Ground estimate: only %d usable pixels outside the roof", candidates.size)
        return None

    return float(np.percentile(candidates, params["ground_percentile"]))


def _snap_to_segment_planes(
    roof_vertices: np.ndarray,
    vertex_lnglat: list[tuple[float, float]],
    building_insights: dict,
    to_local: Transformer,
) -> np.ndarray | None:
    """Replaces measured roof HEIGHTS with each vertex's roof-segment plane.

    Solar API reports, per roof segment, a pitch, an azimuth and a
    planeHeightAtCenterMeters — the plane a real roof section actually
    lies on. Those three numbers describe the roof far better than a
    triangulated DSM does: BASE-tier elevation carries about a metre of
    noise, and where a building has two levels the triangulation ramps
    smoothly between them instead of stepping, so the model renders as a
    hillside rather than a building.

    Snapping each vertex onto its own segment's plane keeps the real
    footprint (x and y are untouched, so the outline, the walls raised
    from it and every panel position stay exactly where the data put
    them) while giving flat sections and honest steps between them.

    Still entirely measured data — Google's plane fit rather than our
    triangulation of Google's raster. Returns None when the response has
    no usable segments, and the caller keeps the DSM surface.
    """
    segments = (building_insights.get("solarPotential") or {}).get("roofSegmentStats") or []
    usable = {}
    for i, seg in enumerate(segments):
        centre = seg.get("center") or {}
        height = seg.get("planeHeightAtCenterMeters")
        if height is None or "latitude" not in centre or "longitude" not in centre:
            continue
        tilt = math.radians(float(seg.get("pitchDegrees") or 0.0))
        azimuth = math.radians(float(seg.get("azimuthDegrees") or 0.0))
        # Plane normal for a surface facing bearing A at pitch T.
        normal = (
            math.sin(azimuth) * math.sin(tilt),
            math.cos(azimuth) * math.sin(tilt),
            math.cos(tilt),
        )
        if abs(normal[2]) < 1e-6:  # a vertical "roof" has no height field
            continue
        cx, cy = to_local.transform(centre["longitude"], centre["latitude"])
        usable[i] = (cx, cy, float(height), normal)

    if not usable:
        return None

    candidates = set(usable)
    snapped = roof_vertices.copy()
    for v, (lng, lat) in enumerate(vertex_lnglat):
        matched = next((i for i in candidates if _segment_contains(segments[i], lng, lat)), None)
        if matched is None:
            matched = _nearest_segment_index(segments, candidates, lng, lat)
        if matched is None:
            continue
        cx, cy, h0, n = usable[matched]
        x, y = snapped[v, 0], snapped[v, 1]
        snapped[v, 2] = h0 - ((x - cx) * n[0] + (y - cy) * n[1]) / n[2]
    return snapped


def _smooth_roof_z(vertices: np.ndarray, faces: np.ndarray, params: dict) -> np.ndarray:
    """Cosmetic Laplacian smoothing of roof HEIGHTS only.

    BASE-tier DSM carries about a metre of noise, which triangulates into
    a crumpled surface with spikes poking up between the panels. Each pass
    blends every vertex's height toward the mean of its neighbours'.

    x and y are deliberately untouched, so the footprint, the roof
    outline the walls are built from, and every panel's plan position all
    stay exactly where the data put them. And this mesh feeds nothing but
    the viewer: area and capacity come from engine/area.py and
    packs/universal.py, which never read it. No reported number moves.
    """
    passes = int(params["roof_smoothing_passes"])
    weight = params["roof_smoothing_weight"]
    if passes <= 0 or weight <= 0 or len(faces) == 0:
        return vertices

    edges = np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    smoothed = vertices.copy()
    for _ in range(passes):
        total = np.zeros(len(smoothed))
        count = np.zeros(len(smoothed))
        np.add.at(total, edges[:, 0], smoothed[edges[:, 1], 2])
        np.add.at(count, edges[:, 0], 1)
        np.add.at(total, edges[:, 1], smoothed[edges[:, 0], 2])
        np.add.at(count, edges[:, 1], 1)
        neighbour_mean = np.where(count > 0, total / np.maximum(count, 1), smoothed[:, 2])
        smoothed[:, 2] = (1 - weight) * smoothed[:, 2] + weight * neighbour_mean
    return smoothed


def _roof_outline(roof_vertices: np.ndarray):
    """The building footprint the walls are built from, taken from the
    roof mesh itself rather than from GEO-04's boundary.

    The boundary is a bounding box, and _keep_roof_samples then trims the
    roof down to the actual building. Extruding walls from the box while
    the roof covers only part of it left the roof sitting inside a grey
    picture frame with a moat around it — the two no longer described the
    same building. Delaunay already spans the convex hull of the retained
    samples, so that hull IS the roof's edge, and walls raised from it
    meet the roof exactly.
    """
    hull = MultiPoint([tuple(xy) for xy in roof_vertices[:, :2]]).convex_hull
    # The raw hull of a noisy point cloud has dozens of near-collinear
    # vertices, which extrudes into a barrel rather than a building.
    # Simplifying to the metre collapses those into the handful of real
    # corners, without moving any of them further than that.
    simplified = hull.simplify(_OUTLINE_SIMPLIFY_M, preserve_topology=True)
    return simplified if simplified.geom_type == "Polygon" and not simplified.is_empty else hull


def _faces_within(vertices: np.ndarray, faces: np.ndarray, outline) -> np.ndarray:
    """Keeps only the triangles whose centroid lies inside `outline`.

    Used to trim the roof to the simplified building footprint the walls
    are raised from. Centroid rather than all-three-vertices: a triangle
    straddling the edge belongs to whichever side its bulk is on, which
    leaves a clean boundary instead of a saw-tooth of dropped slivers.
    """
    centroids = vertices[faces].mean(axis=1)
    inside = shapely_contains_xy(outline, centroids[:, 0], centroids[:, 1])
    return faces[inside]


def _wall_mesh(outline, roof_vertices: np.ndarray, ground_z: float) -> trimesh.Trimesh | None:
    """VIZ-01. Extrudes the roof's own outline straight down to
    `ground_z`, closing the building sides. The top edge follows the DSM
    surface — each perimeter point takes its elevation from the roof mesh
    above it — so the walls meet the roof instead of cutting a flat line
    through it."""
    if outline.geom_type != "Polygon" or outline.is_empty:
        return None
    ring = outline.exterior
    # Segmentize so a long straight wall still tracks an undulating roof
    # edge rather than interpolating between two distant corners.
    with contextlib.suppress(AttributeError):
        ring = ring.segmentize(_WALL_SEGMENT_M)

    points = list(ring.coords)
    if len(points) > 1 and points[0] == points[-1]:
        points = points[:-1]  # closed ring — drop the duplicated closing point
    if len(points) < 3:
        return None

    vertices, faces = [], []
    for x, y in points:
        vertices.append([x, y, _nearest_roof_z(roof_vertices, x, y)])
        vertices.append([x, y, ground_z])

    count = len(points)
    for i in range(count):
        top_a, bot_a = 2 * i, 2 * i + 1
        top_b, bot_b = 2 * ((i + 1) % count), 2 * ((i + 1) % count) + 1
        faces.append([bot_a, bot_b, top_b])
        faces.append([bot_a, top_b, top_a])

    mesh = trimesh.Trimesh(
        vertices=np.array(vertices), faces=np.array(faces, dtype=int), process=False
    )
    mesh.visual.vertex_colors = np.tile(_WALL_COLOR, (len(mesh.vertices), 1)).astype("uint8")
    return mesh


def _ground_mesh(outline, ground_z: float, params: dict[str, float]) -> trimesh.Trimesh:
    """VIZ-01. Two triangles under the building, out to a configured
    margin. Deliberately flat and featureless: BASE-tier DSM around the
    footprint does not support modelled terrain, and inventing some would
    misrepresent the source data."""
    margin = params["ground_margin_m"]
    min_x, min_y, max_x, max_y = outline.bounds
    min_x, min_y = min_x - margin, min_y - margin
    max_x, max_y = max_x + margin, max_y + margin

    vertices = np.array(
        [
            [min_x, min_y, ground_z],
            [max_x, min_y, ground_z],
            [max_x, max_y, ground_z],
            [min_x, max_y, ground_z],
        ]
    )
    mesh = trimesh.Trimesh(vertices=vertices, faces=np.array([[0, 1, 2], [0, 2, 3]]), process=False)
    mesh.visual.vertex_colors = np.tile(_GROUND_COLOR, (4, 1)).astype("uint8")
    return mesh


def _panel_module(
    width_m: float, length_m: float, thickness: float, params: dict[str, float]
) -> trimesh.Trimesh:
    """One photovoltaic module, flat in the XY plane and centred on the
    origin, ready to be tilted and placed.

    Built as a real module is: a dark laminate sitting inside a lighter
    aluminium frame. A single flat-coloured slab per panel is what made
    the first version render as one navy mass — the Solar API packs panel
    centres exactly one panel-width apart, so at full nominal size every
    module touches its neighbours and the array fuses into a slab. Two
    things fix that, and neither invents a position: each module is
    rendered inset by the real clamp gap, and the frame border gives every
    module its own visible edge.
    """
    gap = params["panel_gap_m"]
    frame_m = params["panel_frame_m"]
    outer_w, outer_l = max(width_m - gap, 0.05), max(length_m - gap, 0.05)

    frame = trimesh.creation.box(extents=(outer_w, outer_l, thickness))
    frame.visual.vertex_colors = np.tile(_PANEL_FRAME_COLOR, (len(frame.vertices), 1)).astype(
        "uint8"
    )

    # The laminate: inset by the frame width and sitting ON TOP of the
    # frame body, not merely thicker than it.
    #
    # The first attempt made the glass a slightly deeper box sharing the
    # frame's centre, clearing the frame's top face by 4 mm along the
    # panel's own normal. On a tilted panel that is not enough: the frame
    # is wider in plan, so its upslope edge rises above the glass anyway
    # and the module renders silver from above. Measured on a real
    # 51-panel array — topmost vertex was frame at z=20.6143, glass 8 mm
    # under it at 20.6059.
    #
    # Sitting the slab on the frame's top face instead gives an
    # unambiguous 8 mm of separation that survives any tilt and any
    # depth-buffer precision.
    glass = trimesh.creation.box(
        extents=(
            max(outer_w - 2 * frame_m, 0.02),
            max(outer_l - 2 * frame_m, 0.02),
            _PANEL_GLASS_DEPTH_M,
        )
    )
    glass.apply_translation([0.0, 0.0, thickness / 2 + _PANEL_GLASS_PROUD_M])
    glass.visual.vertex_colors = np.tile(_PANEL_GLASS_COLOR, (len(glass.vertices), 1)).astype(
        "uint8"
    )

    return trimesh.util.concatenate([frame, glass])


def _panel_mesh(
    building_insights: dict,
    to_local: Transformer,
    roof_vertices: np.ndarray,
    params: dict[str, float],
    outline=None,
) -> tuple[trimesh.Trimesh | None, int]:
    """VIZ-01. Places the REAL Solar API panel layout on the roof —
    solarPotential.solarPanels[], one entry per panel, each at its own
    centre and orientation, sized by the response's own
    panelHeight/WidthMeters and tilted by its roof segment's
    pitch/azimuth. Nothing here is a generic arrangement: no layout in the
    response means no panels, never an invented one.

    This is Google's layout, NOT P2's — see the module docstring on why P2
    has nothing to place and why the two capacity figures differ.

    Returns (mesh, panel_count); (None, 0) when the response carries no
    usable layout.
    """
    potential = building_insights.get("solarPotential") or {}
    panels = potential.get("solarPanels") or []
    panel_h, panel_w = potential.get("panelHeightMeters"), potential.get("panelWidthMeters")
    if not panels or not panel_h or not panel_w:
        return None, 0

    segments = potential.get("roofSegmentStats") or []
    thickness = params["panel_thickness_m"]
    clearance = params["panel_clearance_m"]

    # One template per orientation, copied per panel — building the module
    # geometry 57 times over would be pure waste.
    templates = {
        portrait: _panel_module(
            *((panel_w, panel_h) if portrait else (panel_h, panel_w)), thickness, params
        )
        for portrait in (True, False)
    }

    modules = []
    skipped = 0
    for panel in panels:
        center = panel.get("center") or {}
        lat, lng = center.get("latitude"), center.get("longitude")
        if lat is None or lng is None:
            continue

        index = panel.get("segmentIndex")
        segment = segments[index] if isinstance(index, int) and 0 <= index < len(segments) else {}
        tilt = math.radians(float(segment.get("pitchDegrees") or 0.0))
        azimuth = math.radians(float(segment.get("azimuthDegrees") or 0.0))

        # PORTRAIT runs the long side up the slope (local +Y before
        # rotation, which is the tilt direction); LANDSCAPE runs it across.
        module = templates[panel.get("orientation", "PORTRAIT") != "LANDSCAPE"].copy()
        # Tilt about +X (the normal leans to -Y), then swing to the
        # segment's compass azimuth. theta = pi - azimuth carries the
        # tilted normal (0, -sinT, cosT) to (sinA sinT, cosA sinT, cosT),
        # the standard normal for a plane facing bearing A at pitch T.
        module.apply_transform(trimesh.transformations.rotation_matrix(tilt, [1, 0, 0]))
        module.apply_transform(
            trimesh.transformations.rotation_matrix(math.pi - azimuth, [0, 0, 1])
        )

        x, y = to_local.transform(lng, lat)
        # A panel with no roof under it would hang in mid-air off the
        # building's edge, mounted at whatever the nearest roof vertex
        # happened to be. Skip it rather than float it: better to show
        # fewer panels than to show one standing on nothing.
        if outline is not None and not shapely_contains_xy(outline, x, y):
            skipped += 1
            continue
        module.apply_translation([x, y, _nearest_roof_z(roof_vertices, x, y) + clearance])
        modules.append(module)

    if skipped:
        logger.info(
            "Panel layout: %d of %d panels fell outside the rendered roof and were skipped",
            skipped,
            len(panels),
        )

    if not modules:
        return None, 0

    # One merged mesh rather than N nodes — same pixels, a single draw call.
    # Frame and glass are distinguished by vertex colour, so the whole array
    # still needs only one material.
    return trimesh.util.concatenate(modules), len(modules)


def _building_height(roof_vertices: np.ndarray, ground_z: float | None, params: dict) -> float:
    """Roof-minus-ground, sanity-bounded. A DSM artifact outside the
    configured bounds is discarded for the fallback height rather than
    exported as a hundred-metre cliff (VIZ-03: degrade honestly)."""
    if ground_z is None:
        return params["fallback_building_height_m"]
    height = float(np.median(roof_vertices[:, 2])) - ground_z
    if not params["min_building_height_m"] <= height <= params["max_building_height_m"]:
        logger.info(
            "Ground estimate gave an implausible %.1f m building — using the fallback height",
            height,
        )
        return params["fallback_building_height_m"]
    return height


def generate_panorama(
    boundary: dict, weather: dict | None, params: dict | None = None
) -> PanoramaResult:
    """VIZ-01..05. Builds a 3D model of the building — roof, walls, ground
    and the real Solar API panel layout — from `boundary` plus Solar API
    DSM elevation, exports it as a .glb scene, and uploads it to object
    storage.

    Never raises. Any failure (missing DSM, too sparse to triangulate,
    storage unconfigured/unreachable) degrades to an explicit
    not_generated result (VIZ-03). Partial data degrades in parts: no
    ground estimate falls back to a configured height, and no panel layout
    exports the building alone — neither is fabricated.
    """
    try:
        boundary_geom = shape(boundary)
        centroid = boundary_geom.centroid
        lng, lat = centroid.x, centroid.y
        build_params = get_panorama_build_params()

        from solarfit.providers.vision import _download_geotiff_bytes, fetch_solar_api_datalayers

        layers = fetch_solar_api_datalayers(lat, lng)
        dsm_url = layers.get("dsmUrl")
        if not dsm_url:
            return PanoramaResult(
                status="not_generated", reason="No dsmUrl in Data Layers response"
            )
        dsm_bytes = _download_geotiff_bytes(dsm_url)

        # Ground first: the roof/ground split below is keyed on it.
        to_local = _local_transformer(boundary_geom)
        ground_z = _ground_elevation(dsm_bytes, boundary_geom, to_local, build_params)

        roof_vertices, roof_faces, vertex_lnglat = _mesh_from_dsm(
            dsm_bytes, boundary_geom, ground_z
        )
        if len(roof_faces) == 0:
            return PanoramaResult(
                status="not_generated", reason="Elevation grid too sparse to triangulate"
            )

        # Building Insights feeds the roof planes, the panel layout AND the
        # shading tint, so it is fetched once, before the surface is
        # finalised. Best-effort in its own try/except: none of the three
        # is worth failing an otherwise-real building over (VIZ-03).
        building_insights: dict = {}
        try:
            from solarfit.providers.vision import fetch_building_insights

            building_insights = fetch_building_insights(lat, lng)
        except Exception:
            logger.warning(
                "Building Insights unavailable — no panels, no shading tint", exc_info=True
            )

        # Prefer Google's own per-segment plane fit over our triangulation
        # of their raster; fall back to the DSM surface when the response
        # carries no segments. Smoothing only matters for the DSM path —
        # a plane is already flat.
        planar = _snap_to_segment_planes(roof_vertices, vertex_lnglat, building_insights, to_local)
        if planar is not None:
            roof_vertices = planar
        else:
            logger.info("No roof segments — keeping the DSM surface")
            roof_vertices = _smooth_roof_z(roof_vertices, roof_faces, build_params)

        height = _building_height(roof_vertices, ground_z, build_params)

        # Re-base every Z so ground sits at 0 and the roof at its real
        # height above it. Absolute DSM elevation (~518 m at Hyderabad)
        # would otherwise put the whole model half a kilometre off the
        # origin, wrecking the viewer's default framing for no gain.
        roof_base = float(np.median(roof_vertices[:, 2])) - height
        roof_vertices = roof_vertices.copy()
        roof_vertices[:, 2] -= roof_base

        # Walls and ground both key off the roof's own outline, so all
        # three parts describe one building (see _roof_outline).
        outline = _roof_outline(roof_vertices)
        # Simplifying the hull pulls the outline INSIDE the roof's true
        # edge, so the roof would otherwise hang raggedly over the walls.
        # Dropping the faces that fall outside trims it back to the same
        # footprint the walls rise to, and roof and walls meet cleanly.
        roof_faces = _faces_within(roof_vertices, roof_faces, outline)
        if len(roof_faces) == 0:
            return PanoramaResult(
                status="not_generated", reason="Roof outline left no usable surface"
            )

        roof = trimesh.Trimesh(vertices=roof_vertices, faces=roof_faces, process=False)
        vertex_colors = _vertex_colors_from_segments(vertex_lnglat, building_insights)
        if vertex_colors is not None:
            roof.visual.vertex_colors = vertex_colors

        # Every node carries the Z-up -> Y-up conversion; see _gltf_y_up().
        y_up = _gltf_y_up()
        scene = trimesh.Scene()
        scene.add_geometry(roof, geom_name="Roof", node_name="Roof", transform=y_up)

        walls = _wall_mesh(outline, roof_vertices, ground_z=0.0)
        if walls is not None:
            scene.add_geometry(walls, geom_name="Walls", node_name="Walls", transform=y_up)

        scene.add_geometry(
            _ground_mesh(outline, 0.0, build_params),
            geom_name="Ground",
            node_name="Ground",
            transform=y_up,
        )

        panels, panel_count = _panel_mesh(
            building_insights, to_local, roof_vertices, build_params, outline
        )
        if panels is not None:
            scene.add_geometry(
                panels, geom_name="SolarPanels", node_name="SolarPanels", transform=y_up
            )
        else:
            logger.info(
                "No solarPanels[] layout at (%s, %s) — exporting the building alone", lat, lng
            )

        glb_bytes = scene.export(file_type="glb")
        version_hash = _boundary_version_hash(boundary)
        logger.info(
            "Panorama %s: %d panels, %.1f m tall, ground %s, %d bytes",
            version_hash,
            panel_count,
            height,
            "measured" if ground_z is not None else "fallback",
            len(glb_bytes),
        )

        from solarfit.providers.storage import upload_glb

        url = upload_glb(glb_bytes, key=f"panorama/{version_hash}.glb")
        if url is None:
            return PanoramaResult(
                status="not_generated", reason="Object storage not configured or upload failed"
            )

        return PanoramaResult(
            url=url, status="ok", generated_at=datetime.now(UTC), version=version_hash
        )

    except Exception:
        logger.exception("Panorama generation failed")
        return PanoramaResult(
            status="not_generated", reason="Unexpected failure during panorama generation"
        )
