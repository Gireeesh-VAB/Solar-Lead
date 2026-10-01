"""§16 Testing — Day 4 implementation of §9.12 3D Visualization
(VIZ-01..05).

_mesh_from_dsm() is exercised against a real synthetic in-memory DSM
GeoTIFF with a known geotransform — an integration test of the actual
rasterio crop + triangulation + trimesh export, not a mock.
generate_panorama() mocks providers.vision's Solar API calls and
providers.storage.upload_glb — no live network calls in the automated
suite.
"""

import math
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import trimesh
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from shapely.affinity import rotate
from shapely.geometry import MultiPoint, shape
from shapely.geometry import box as shapely_box
from shapely.ops import transform as shapely_transform

from solarfit.engine.panel_packing import pack_panels
from solarfit.engine.panorama import (
    _ROOF_EXTENSION_COLOR,
    FACES_PER_PANEL,
    VERTICES_PER_PANEL,
    _boundary_version_hash,
    _mesh_from_dsm,
    _nearest_roof_z,
    _vertex_colors_from_segments,
    build_scene_geometry,
    generate_panorama,
)
from solarfit.packs.config_pack import get_panorama_build_params

WEST, SOUTH, EAST, NORTH = 78.4860, 17.3845, 78.4874, 17.3855
WIDTH_PX, HEIGHT_PX = 60, 60


def _make_synthetic_dsm() -> bytes:
    """A single-band float32 GeoTIFF covering WEST/SOUTH/EAST/NORTH with
    a gentle west-to-east elevation gradient (400m..410m) — real
    elevation-shaped data, not a flat/empty raster."""
    transform = from_bounds(WEST, SOUTH, EAST, NORTH, WIDTH_PX, HEIGHT_PX)
    gradient = np.linspace(400.0, 410.0, WIDTH_PX, dtype="float32")
    data = np.tile(gradient, (HEIGHT_PX, 1))

    with MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            height=HEIGHT_PX,
            width=WIDTH_PX,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=transform,
            nodata=-9999.0,
        ) as dataset:
            dataset.write(data, 1)
        return memfile.read()


def _boundary_covering_center_quarter() -> dict:
    mid_lng = (WEST + EAST) / 2
    mid_lat = (SOUTH + NORTH) / 2
    quarter_lng = (EAST - WEST) / 4
    quarter_lat = (NORTH - SOUTH) / 4
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [mid_lng - quarter_lng, mid_lat - quarter_lat],
                [mid_lng + quarter_lng, mid_lat - quarter_lat],
                [mid_lng + quarter_lng, mid_lat + quarter_lat],
                [mid_lng - quarter_lng, mid_lat + quarter_lat],
                [mid_lng - quarter_lng, mid_lat - quarter_lat],
            ]
        ],
    }


def _make_two_level_dsm() -> bytes:
    """A DSM with two distinct height bands — a low ~400 m 'courtyard'
    covering the west half, a tall ~415 m 'roof' covering the east half.
    Mirrors a real check found in review (2026-09-10): a site whose
    drawn boundary legitimately contains both a low, non-roof area and a
    taller building, where the DSM roof extraction correctly excludes
    the low part and _roof_outline() ends up narrower than the site
    boundary — the gap _roof_extension_mesh() exists to cap."""
    transform = from_bounds(WEST, SOUTH, EAST, NORTH, WIDTH_PX, HEIGHT_PX)
    data = np.full((HEIGHT_PX, WIDTH_PX), 400.0, dtype="float32")
    data[:, WIDTH_PX // 2 :] = 415.0  # east half is the tall roof
    with MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            height=HEIGHT_PX,
            width=WIDTH_PX,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=transform,
            nodata=-9999.0,
        ) as dataset:
            dataset.write(data, 1)
        return memfile.read()


def _boundary_covering_east_two_thirds() -> dict:
    """Covers the tall east half plus a chunk of the low west half — a
    boundary bigger than the real (tall-only) roof, same shape as a
    real site whose drawn boundary includes a courtyard/lower wing
    beside the building."""
    west_third = WEST + (EAST - WEST) / 3
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [west_third, SOUTH],
                [EAST, SOUTH],
                [EAST, NORTH],
                [west_third, NORTH],
                [west_third, SOUTH],
            ]
        ],
    }


def test_build_scene_geometry_caps_the_gap_between_dsm_roof_and_site_boundary():
    boundary = _boundary_covering_east_two_thirds()
    dsm_bytes = _make_two_level_dsm()

    with _patch_dsm_fetch(dsm_bytes):
        result = build_scene_geometry(boundary)

    assert result.status == "ok"
    assert result.roof.colors is not None
    extension_rgb = tuple(round(c / 255, 6) for c in _ROOF_EXTENSION_COLOR[:3])
    assert any(
        tuple(round(c, 6) for c in color) == extension_rgb for color in result.roof.colors
    ), "expected a roof-extension cap over the low/high boundary gap"

    # Walls now reach the real (wider) boundary, and thanks to the cap
    # above, the roof mesh's own vertices now reach that same edge too
    # (the extension's boundary-ring points are part of it) — no gap
    # left between where the walls stand and where the roof covers them.
    wall_x = [v[0] for v in result.walls.vertices]
    roof_x = [v[0] for v in result.roof.vertices]
    assert min(roof_x) == pytest.approx(min(wall_x), abs=0.01)
    assert max(roof_x) == pytest.approx(max(wall_x), abs=0.01)


def _patch_dsm_fetch(dsm_bytes: bytes):
    # fetch_building_insights defaults to "no shading data" — tests that
    # care about tinting override it explicitly (list this helper first
    # in the `with (...)` tuple so an explicit override applied after it
    # wins).
    return patch.multiple(
        "solarfit.providers.vision",
        fetch_solar_api_datalayers=MagicMock(
            return_value={"dsmUrl": "https://example.com/dsm.tif"}
        ),
        _download_geotiff_bytes=MagicMock(return_value=dsm_bytes),
        fetch_building_insights=MagicMock(return_value={}),
    )


def test_generate_panorama_produces_real_glb_and_uploads():
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()

    with (
        _patch_dsm_fetch(dsm_bytes),
        patch(
            "solarfit.providers.storage.upload_glb",
            return_value="https://storage.example.com/p/x.glb",
        ) as upload,
    ):
        result = generate_panorama(boundary, weather=None)

    assert result.status == "ok"
    assert result.url == "https://storage.example.com/p/x.glb"
    assert result.version == _boundary_version_hash(boundary)
    assert result.generated_at is not None

    upload.assert_called_once()
    glb_bytes = upload.call_args[0][0]
    assert (
        glb_bytes[:4] == b"glTF"
    )  # a real, valid glTF-binary export, not a fabricated placeholder


def test_generate_panorama_missing_dsm_url_is_not_generated():
    boundary = _boundary_covering_center_quarter()

    with patch.multiple(
        "solarfit.providers.vision",
        fetch_solar_api_datalayers=MagicMock(return_value={}),
        _download_geotiff_bytes=MagicMock(),
    ):
        result = generate_panorama(boundary, weather=None)

    assert result.status == "not_generated"  # VIZ-03: never fabricate a mesh
    assert result.url is None


def test_generate_panorama_upload_failure_is_not_generated():
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()

    with (
        _patch_dsm_fetch(dsm_bytes),
        patch("solarfit.providers.storage.upload_glb", return_value=None),
    ):
        result = generate_panorama(boundary, weather=None)

    assert result.status == "not_generated"
    assert result.url is None


def test_build_scene_geometry_produces_json_roof_and_walls():
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()

    with _patch_dsm_fetch(dsm_bytes):
        result = build_scene_geometry(boundary)

    assert result.status == "ok"
    assert result.version == _boundary_version_hash(boundary)
    assert result.roof is not None
    assert len(result.roof.vertices) > 0
    assert len(result.roof.faces) > 0
    assert all(len(face) == 3 for face in result.roof.faces)
    max_index = max(i for face in result.roof.faces for i in face)
    assert max_index < len(result.roof.vertices)  # every face index resolves to a real vertex

    assert result.ground_source in ("measured", "fallback")
    assert result.height_m is not None
    assert result.walls is None or len(result.walls.vertices) > 0


def test_build_scene_geometry_never_touches_the_glb_pipeline():
    """build_scene_geometry() and generate_panorama() are independent
    reads of the same helpers — running one must not change what the
    other produces."""
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()

    with (
        _patch_dsm_fetch(dsm_bytes),
        patch(
            "solarfit.providers.storage.upload_glb",
            return_value="https://storage.example.com/p/x.glb",
        ),
    ):
        build_scene_geometry(boundary)
        glb_result = generate_panorama(boundary, weather=None)

    assert glb_result.status == "ok"
    assert glb_result.url == "https://storage.example.com/p/x.glb"


def test_build_scene_geometry_missing_dsm_url_is_not_generated():
    boundary = _boundary_covering_center_quarter()

    with patch.multiple(
        "solarfit.providers.vision",
        fetch_solar_api_datalayers=MagicMock(return_value={}),
        _download_geotiff_bytes=MagicMock(),
    ):
        result = build_scene_geometry(boundary)

    assert result.status == "not_generated"  # VIZ-03: never fabricate a mesh
    assert result.roof is None


def _app_packed_panel_layout(count: int = 3) -> dict:
    """A minimal routers/assessments.py::_pack_panel_layout()-shaped
    panel_layout dict — real corners (a small WGS84 rectangle per panel),
    not Google's solarPanels[]."""
    mid_lng = (WEST + EAST) / 2
    mid_lat = (SOUTH + NORTH) / 2
    dlng, dlat = 0.00001, 0.00002
    return {
        "status": "ok",
        "panels": [
            {
                "corners": [
                    [mid_lng + i * 0.00003 - dlng, mid_lat - dlat],
                    [mid_lng + i * 0.00003 + dlng, mid_lat - dlat],
                    [mid_lng + i * 0.00003 + dlng, mid_lat + dlat],
                    [mid_lng + i * 0.00003 - dlng, mid_lat + dlat],
                ],
                "segmentIndex": 0,
                "azimuthDeg": _PANEL_AZIMUTH_DEG,
                "tiltDeg": _PANEL_TILT_DEG,
            }
            for i in range(count)
        ],
    }


def _app_packed_panel_layout_with_tilt(count: int, tilt_deg: float) -> dict:
    """Same shape as _app_packed_panel_layout(), with an overridden tilt —
    used to exercise the flat-roof-vs-sloped mounting-leg branch in
    _panel_mesh_from_layout()."""
    layout = _app_packed_panel_layout(count)
    for panel in layout["panels"]:
        panel["tiltDeg"] = tilt_deg
    return layout


def _applied_obstacle_near_center() -> dict:
    mid_lng = (WEST + EAST) / 2
    mid_lat = (SOUTH + NORTH) / 2
    dlng, dlat = 0.00004, 0.00004
    ring = [
        [mid_lng - dlng, mid_lat - dlat],
        [mid_lng + dlng, mid_lat - dlat],
        [mid_lng + dlng, mid_lat + dlat],
        [mid_lng - dlng, mid_lat + dlat],
        [mid_lng - dlng, mid_lat - dlat],
    ]
    return {
        "id": "obstacle-1",
        "type": "water_tank",
        "bounding_polygon": {"type": "Polygon", "coordinates": [ring]},
    }


def test_build_scene_geometry_places_the_app_packed_panel_array():
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()

    with _patch_dsm_fetch(dsm_bytes):
        result = build_scene_geometry(boundary, panel_layout=_app_packed_panel_layout(3))

    assert result.status == "ok"
    assert result.panel_count == 3
    assert result.panels is not None
    assert len(result.panels.vertices) > 0
    assert len(result.panels.faces) > 0
    # Panel frame/glass colouring (_panel_module()) carries through as
    # per-vertex colors, same as the .glb path's own panel array.
    assert result.panels.colors is not None
    assert len(result.panels.colors) == len(result.panels.vertices)

    # Panels sit ON the roof, not floating above it or buried in it — same
    # tolerance test_panels_sit_on_the_roof_not_floating_or_buried() uses
    # against the .glb pipeline's own panel placement.
    roof_z_range = (min(v[2] for v in result.roof.vertices), max(v[2] for v in result.roof.vertices))
    panel_z = [v[2] for v in result.panels.vertices]
    assert min(panel_z) >= roof_z_range[0] - 0.5
    assert max(panel_z) <= roof_z_range[1] + 1.0


def test_build_scene_geometry_flat_panels_get_mounting_legs():
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()

    with _patch_dsm_fetch(dsm_bytes):
        result = build_scene_geometry(
            boundary, panel_layout=_app_packed_panel_layout_with_tilt(3, tilt_deg=0.0)
        )

    assert result.status == "ok"
    assert result.mounting is not None
    assert len(result.mounting.vertices) > 0
    assert len(result.mounting.faces) > 0
    assert result.mounting.colors is not None

    # Legs sit at or above the roof and no higher than the panels they
    # support — same floating/buried discipline as the panel placement
    # check above.
    roof_z_range = (min(v[2] for v in result.roof.vertices), max(v[2] for v in result.roof.vertices))
    leg_z = [v[2] for v in result.mounting.vertices]
    assert min(leg_z) >= roof_z_range[0] - 0.5
    assert max(leg_z) <= roof_z_range[1] + 1.0


def test_build_scene_geometry_sloped_panels_get_no_mounting_legs():
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()

    with _patch_dsm_fetch(dsm_bytes):
        # Default fixture tilt (_PANEL_TILT_DEG = 20.0) is well above the
        # flat-roof threshold — already sits flush to its own roof plane
        # and needs no separate rack visual.
        result = build_scene_geometry(boundary, panel_layout=_app_packed_panel_layout(3))

    assert result.status == "ok"
    assert result.mounting is None


def test_build_scene_geometry_no_panel_layout_means_no_panels():
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()

    with _patch_dsm_fetch(dsm_bytes):
        result = build_scene_geometry(boundary)

    assert result.status == "ok"
    assert result.panels is None
    assert result.panel_count == 0


def _rotated_panel_layout_entry(
    to_wgs84, *, cx: float, cy: float, across: float, along: float, tilt_deg: float, azimuth_deg: float
) -> dict:
    """One panel footprint built exactly the way engine/panel_packing.py::
    pack_panels() builds one — an axis-aligned box rotated into place with
    shapely.affinity.rotate(candidate, azimuth_deg) — so its corners are
    self-consistent with what a real packed layout actually produces. A
    fixture that instead hands out an UNROTATED square regardless of the
    azimuthDeg it's labelled with (this test's old fixture) tests a data
    shape pack_panels() could never produce, and would not have caught the
    axis-swap / azimuth-convention bugs the two fix comments in
    _panel_mesh_from_layout() describe — both only show up once a panel's
    corners actually encode its own rotation."""
    box_geom = shapely_box(cx - across / 2, cy - along / 2, cx + across / 2, cy + along / 2)
    rotated = rotate(box_geom, azimuth_deg, origin=(cx, cy), use_radians=False)
    ring = list(rotated.exterior.coords)[:4]
    return {
        "corners": [list(to_wgs84(x, y)) for x, y in ring],
        "tiltDeg": tilt_deg,
        "azimuthDeg": azimuth_deg,
    }


def test_build_scene_geometry_multi_plane_panels_keep_independent_orientation():
    """A layout with panels on two different roof planes (different
    tiltDeg/azimuthDeg — as _pack_panel_layout() produces packing more
    than one Building Insights roof segment) must place each panel at ITS
    OWN orientation, never a shared/averaged one across the array — and
    that orientation must match what a rigid tilt-then-swing rotation of
    ITS OWN real footprint actually produces (see _panel_mesh_from_layout()'s
    swing-from-corners fix comment), not a value re-derived from the raw
    azimuthDeg number, which is not the same rotation for a real packed
    layout. Recovers each panel's surface normal from the exported JSON
    mesh, same technique test_panel_tilt_and_azimuth_come_from_the_roof_
    segment() uses for the .glb pipeline's own (differently-sourced,
    differently-rotated) panels."""
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()
    boundary_geom = shape(boundary)
    centroid = boundary_geom.centroid
    local_crs = f"+proj=aeqd +lat_0={centroid.y} +lon_0={centroid.x} +datum=WGS84 +units=m +no_defs"
    to_wgs84 = Transformer.from_crs(local_crs, "EPSG:4326", always_xy=True).transform

    specs = [(-3.0, 12.0, 90.0), (3.0, 30.0, 250.0)]  # (cx, tilt_deg, azimuth_deg) — spaced well apart
    layout = {
        "panels": [
            _rotated_panel_layout_entry(
                to_wgs84, cx=cx, cy=0.0, across=1.0, along=1.9, tilt_deg=tilt_deg, azimuth_deg=azimuth_deg
            )
            for cx, tilt_deg, azimuth_deg in specs
        ]
    }

    with _patch_dsm_fetch(dsm_bytes):
        result = build_scene_geometry(boundary, panel_layout=layout)

    assert result.status == "ok"
    assert result.panel_count == 2

    verts = np.array(result.panels.vertices)
    faces = np.array(result.panels.faces)

    for i, (_cx, tilt_deg, azimuth_deg) in enumerate(specs):
        v_start = i * VERTICES_PER_PANEL
        f_start = i * FACES_PER_PANEL
        panel_verts = verts[v_start : v_start + VERTICES_PER_PANEL]
        panel_faces = faces[f_start : f_start + FACES_PER_PANEL] - v_start
        mesh = trimesh.Trimesh(vertices=panel_verts, faces=panel_faces, process=False)

        largest = mesh.area_faces > mesh.area_faces.max() * 0.9
        up_facing = mesh.face_normals[largest][mesh.face_normals[largest][:, 2] > 0]
        normal = up_facing.mean(axis=0)
        normal /= np.linalg.norm(normal)

        tilt = np.degrees(np.arccos(np.clip(normal[2], -1, 1)))
        azimuth = np.degrees(np.arctan2(normal[0], normal[1])) % 360

        # Closed-form expectation for a plane tilted about +X by tilt_deg
        # then swung about +Z by azimuth_deg (the SAME rotation
        # pack_panels() applies to place this panel's own footprint),
        # independent of the render pipeline itself.
        t, phi = math.radians(tilt_deg), math.radians(azimuth_deg)
        expected_normal = np.array([math.sin(t) * math.sin(phi), -math.sin(t) * math.cos(phi), math.cos(t)])
        expected_azimuth = np.degrees(np.arctan2(expected_normal[0], expected_normal[1])) % 360

        assert tilt == pytest.approx(tilt_deg, abs=0.5)
        assert azimuth == pytest.approx(expected_azimuth, abs=1.0)


# ---------------------------------------------------------------------------
# Regression: _panel_mesh_from_layout() must never render overlapping
# panels. _app_packed_panel_layout() above uses small near-square synthetic
# footprints (a few cm across), which never exercised a REAL portrait
# module's actual aspect ratio (much longer than it is wide) — that
# realistic elongation is exactly what exposed the axis-swap bug (see the
# fix comment in _panel_mesh_from_layout()): the up-slope edge and the
# across-row edge were fed into the wrong axes of _panel_module(), so
# every module tilted sideways across its row instead of up its own
# slope, with no clearance ever reserved for that, and adjacent panels
# intersected. These tests use engine/panel_packing.py's own real
# pack_panels() — a genuine multi-row, multi-column layout with real
# panel dimensions — round-tripped through the exact local<->WGS84 frame
# build_scene_geometry() itself uses, the same way routers/assessments.py::
# _pack_panel_layout() feeds it in production.
# ---------------------------------------------------------------------------

_REALISTIC_PANEL_LENGTH_M = 1.879  # up-slope edge — much longer than the width
_REALISTIC_PANEL_WIDTH_M = 1.045  # across-row edge


def _real_packed_panel_layout(
    boundary: dict,
    *,
    tilt_deg: float,
    azimuth_deg: float = 180.0,
    side_m: float = 8.0,
    orientation: str = "portrait",
) -> dict:
    """A real, multi-row/multi-column PackedLayout packed into a small
    square centred on `boundary`'s own centroid, then converted to the
    same {"corners"/"tiltDeg"/"azimuthDeg"} shape routers/assessments.py::
    _pack_panel_layout() persists — via the identical local-metric<->WGS84
    frame _local_transformer() builds, so every corner round-trips back to
    exactly the local coordinates it was packed at."""
    boundary_geom = shape(boundary)
    centroid = boundary_geom.centroid
    local_crs = (
        f"+proj=aeqd +lat_0={centroid.y} +lon_0={centroid.x} +datum=WGS84 +units=m +no_defs"
    )
    to_wgs84 = Transformer.from_crs(local_crs, "EPSG:4326", always_xy=True).transform

    usable = shapely_box(-side_m / 2, -side_m / 2, side_m / 2, side_m / 2)
    layout = pack_panels(
        usable,
        latitude_deg=centroid.y,
        tilt_deg=tilt_deg,
        azimuth_deg=azimuth_deg,
        panel_length_m=_REALISTIC_PANEL_LENGTH_M,
        panel_width_m=_REALISTIC_PANEL_WIDTH_M,
        panel_watts=350.0,
        params={"orientation": orientation},
    )
    assert len({p.row for p in layout.panels}) >= 2, "fixture must pack multiple rows"
    assert layout.count >= 6, "fixture must pack multiple columns too"

    panels = [
        {
            "corners": [list(pt) for pt in list(shapely_transform(to_wgs84, panel.footprint).exterior.coords)[:4]],
            "tiltDeg": tilt_deg,
            "azimuthDeg": azimuth_deg,
        }
        for panel in layout.panels
    ]
    return {"panels": panels}


@pytest.mark.parametrize("tilt_deg", [0.0, 20.0, 35.0])
def test_build_scene_geometry_packed_panels_never_overlap(tilt_deg):
    """Flat (0 deg), moderately sloped (20 deg) and steep (35 deg) roofs,
    each with several rows and columns — no two rendered panels'
    horizontal footprints may intersect, and every packed panel must
    survive into the scene (same count, nothing silently dropped)."""
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()
    panel_layout = _real_packed_panel_layout(boundary, tilt_deg=tilt_deg)

    with _patch_dsm_fetch(dsm_bytes):
        result = build_scene_geometry(boundary, panel_layout=panel_layout)

    assert result.status == "ok"
    assert result.panel_count == len(panel_layout["panels"])

    verts = np.array(result.panels.vertices)
    hulls = [
        MultiPoint(verts[i * VERTICES_PER_PANEL : (i + 1) * VERTICES_PER_PANEL, :2]).convex_hull
        for i in range(result.panel_count)
    ]
    for i in range(len(hulls)):
        for j in range(i + 1, len(hulls)):
            overlap = hulls[i].intersection(hulls[j]).area
            assert overlap < 1e-4, (
                f"panels {i} and {j} overlap by {overlap:.4f} m2 at tilt={tilt_deg} deg"
            )


def test_build_scene_geometry_packed_panels_never_overlap_landscape_orientation():
    """Same non-overlap guarantee for LANDSCAPE modules (long edge across
    the row instead of up-slope) — the axis-swap bug's fix must hold
    regardless of which physical dimension ends up 'up-slope'."""
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()
    panel_layout = _real_packed_panel_layout(boundary, tilt_deg=20.0, orientation="landscape")

    with _patch_dsm_fetch(dsm_bytes):
        result = build_scene_geometry(boundary, panel_layout=panel_layout)

    assert result.status == "ok"
    assert result.panel_count == len(panel_layout["panels"])

    verts = np.array(result.panels.vertices)
    hulls = [
        MultiPoint(verts[i * VERTICES_PER_PANEL : (i + 1) * VERTICES_PER_PANEL, :2]).convex_hull
        for i in range(result.panel_count)
    ]
    for i in range(len(hulls)):
        for j in range(i + 1, len(hulls)):
            overlap = hulls[i].intersection(hulls[j]).area
            assert overlap < 1e-4, f"panels {i} and {j} overlap by {overlap:.4f} m2 (landscape)"


def test_build_scene_geometry_places_a_real_obstacle_box():
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()

    with _patch_dsm_fetch(dsm_bytes):
        result = build_scene_geometry(boundary, obstacles=[_applied_obstacle_near_center()])

    assert result.status == "ok"
    assert len(result.obstacles) == 1
    obstacle = result.obstacles[0]
    assert obstacle.id == "obstacle-1"
    assert obstacle.type == "water_tank"
    assert len(obstacle.mesh.vertices) > 0
    assert len(obstacle.mesh.faces) > 0

    # Sits on the roof: its base is within one obstacle-height of the roof
    # surface, not floating in the sky or buried underground.
    z_values = [v[2] for v in obstacle.mesh.vertices]
    roof_z_max = max(v[2] for v in result.roof.vertices)
    assert min(z_values) >= -1.0
    assert max(z_values) <= roof_z_max + 2.0


def test_build_scene_geometry_degenerate_obstacle_polygon_is_skipped():
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()
    bad_obstacle = {
        "id": "bad-1",
        "type": "vent",
        "bounding_polygon": {"type": "Polygon", "coordinates": [[]]},
    }

    with _patch_dsm_fetch(dsm_bytes):
        result = build_scene_geometry(boundary, obstacles=[bad_obstacle])

    assert result.status == "ok"  # a bad obstacle degrades quietly, never fails the whole scene
    assert result.obstacles == []


def test_build_scene_geometry_roof_carries_the_sunshine_heatmap():
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()

    with patch.multiple(
        "solarfit.providers.vision",
        fetch_solar_api_datalayers=MagicMock(return_value={"dsmUrl": "https://example.com/dsm.tif"}),
        _download_geotiff_bytes=MagicMock(return_value=dsm_bytes),
        fetch_building_insights=MagicMock(
            return_value={
                "solarPotential": {
                    "roofSegmentStats": [_BRIGHT_SEGMENT, _DARK_SEGMENT],
                }
            }
        ),
    ):
        result = build_scene_geometry(boundary)

    assert result.status == "ok"
    assert result.roof.colors is not None
    assert len(result.roof.colors) == len(result.roof.vertices)
    # Real, differing colours (not a flat/uniform tint) — matches
    # test_vertex_colors_from_segments_differ_for_differently_lit_segments()
    # against the same two segments.
    assert len({tuple(c) for c in result.roof.colors}) > 1


def test_build_scene_geometry_no_shading_data_means_no_roof_colors():
    """Absent Building Insights, no per-segment sunshine tint should ever
    appear on the roof. The roof mesh can still legitimately carry SOME
    color — _roof_extension_mesh()'s cap over the DSM/boundary gap always
    colours itself _ROOF_EXTENSION_COLOR regardless of shading data — so
    this checks for the specific absence of a fabricated heatmap tint,
    not a blanket absence of any color at all."""
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()

    with _patch_dsm_fetch(dsm_bytes):  # fetch_building_insights defaults to {}
        result = build_scene_geometry(boundary)

    assert result.status == "ok"
    if result.roof.colors is None:
        return  # no gap needed capping on this fixture — the clean case
    extension_rgb = tuple(round(c / 255, 10) for c in _ROOF_EXTENSION_COLOR[:3])
    default_rgb = (0.4, 0.4, 0.4)  # trimesh's own default vertex color
    for color in result.roof.colors:
        assert tuple(round(c, 10) for c in color) in (
            extension_rgb,
            default_rgb,
        ), f"unexpected roof color {color} — looks like a fabricated heatmap tint"


def test_generate_panorama_version_changes_with_boundary():
    boundary_a = _boundary_covering_center_quarter()
    boundary_b = {
        "type": "Polygon",
        "coordinates": [[[lng + 0.0001, lat] for lng, lat in boundary_a["coordinates"][0]]],
    }

    assert _boundary_version_hash(boundary_a) != _boundary_version_hash(boundary_b)


_BRIGHT_SEGMENT = {
    "stats": {"sunshineQuantiles": [1200.0]},
    "boundingBox": {
        "sw": {"longitude": 78.48635, "latitude": 17.38475},
        "ne": {"longitude": 78.4867, "latitude": 17.38525},
    },
}
_DARK_SEGMENT = {
    "stats": {"sunshineQuantiles": [400.0]},
    "boundingBox": {
        "sw": {"longitude": 78.4867, "latitude": 17.38475},
        "ne": {"longitude": 78.48705, "latitude": 17.38525},
    },
}


def test_vertex_colors_from_segments_differ_for_differently_lit_segments():
    vertex_lnglat = [(78.4864, 17.3850), (78.4869, 17.3850)]  # west (bright) / east (dark)
    building_insights = {"solarPotential": {"roofSegmentStats": [_BRIGHT_SEGMENT, _DARK_SEGMENT]}}

    colors = _vertex_colors_from_segments(vertex_lnglat, building_insights)

    assert colors is not None
    assert colors.shape == (2, 4)
    assert not (colors[0] == colors[1]).all()  # differently-lit segments -> different colors
    assert colors[0][0] > colors[1][0]  # brighter segment maps to a "sunnier" colour


def test_vertex_colors_from_segments_returns_none_when_no_segments():
    assert _vertex_colors_from_segments([(78.4864, 17.3850)], {}) is None
    assert (
        _vertex_colors_from_segments(
            [(78.4864, 17.3850)], {"solarPotential": {"roofSegmentStats": []}}
        )
        is None
    )


def test_generate_panorama_applies_shading_tint_without_affecting_result():
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()
    building_insights = {"solarPotential": {"roofSegmentStats": [_BRIGHT_SEGMENT, _DARK_SEGMENT]}}

    with (
        _patch_dsm_fetch(dsm_bytes),
        patch("solarfit.providers.vision.fetch_building_insights", return_value=building_insights),
        patch(
            "solarfit.providers.storage.upload_glb",
            return_value="https://storage.example.com/p/x.glb",
        ) as upload,
    ):
        result = generate_panorama(boundary, weather=None)

    assert result.status == "ok"
    glb_bytes = upload.call_args[0][0]
    assert glb_bytes[:4] == b"glTF"  # still a real, valid export with tinting applied


def test_generate_panorama_shading_fetch_failure_still_succeeds():
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()

    with (
        _patch_dsm_fetch(dsm_bytes),
        patch(
            "solarfit.providers.vision.fetch_building_insights",
            side_effect=RuntimeError("network down"),
        ),
        patch(
            "solarfit.providers.storage.upload_glb",
            return_value="https://storage.example.com/p/x.glb",
        ),
    ):
        result = generate_panorama(boundary, weather=None)

    assert (
        result.status == "ok"
    )  # a shading-tint failure must never fail the whole panorama (VIZ-03)


# ---------------------------------------------------------------------------
# VIZ-01 building assembly — roof + walls + ground + real solar panel layout.
#
# The .glb is a glTF scene of four named meshes. trimesh writes the Y-up
# conversion onto the scene-graph node rather than baking it into the
# meshes, so scene.geometry[name].vertices reads back in the original Z-up
# metric frame these tests assert against.
# ---------------------------------------------------------------------------

_PANEL_TILT_DEG = 20.0
_PANEL_AZIMUTH_DEG = 180.0  # due south


def _building_insights_with_panels(count: int = 3) -> dict:
    """A Solar API response carrying a real-shaped solarPanels[] layout:
    per-panel centres and orientation, global panel dimensions, and a roof
    segment supplying pitch/azimuth."""
    mid_lng = (WEST + EAST) / 2
    mid_lat = (SOUTH + NORTH) / 2
    return {
        "solarPotential": {
            "panelHeightMeters": 1.879,
            "panelWidthMeters": 1.045,
            "panelCapacityWatts": 400,
            "solarPanels": [
                {
                    "center": {"latitude": mid_lat, "longitude": mid_lng + i * 0.00002},
                    "orientation": "PORTRAIT",
                    "segmentIndex": 0,
                }
                for i in range(count)
            ],
            "roofSegmentStats": [
                {
                    "pitchDegrees": _PANEL_TILT_DEG,
                    "azimuthDegrees": _PANEL_AZIMUTH_DEG,
                    "stats": {"sunshineQuantiles": [1500.0]},
                }
            ],
        }
    }


def _generate_scene(building_insights: dict | None = None):
    """Runs the real pipeline against the synthetic DSM and returns the
    reloaded glTF scene — an integration check of export AND reload, not a
    peek at in-memory objects."""
    captured = {}

    def _capture(data, key):
        captured["glb"] = data
        return "https://storage.example.com/p/x.glb"

    patches = [_patch_dsm_fetch(_make_synthetic_dsm())]
    if building_insights is not None:
        patches.append(
            patch(
                "solarfit.providers.vision.fetch_building_insights", return_value=building_insights
            )
        )
    patches.append(patch("solarfit.providers.storage.upload_glb", side_effect=_capture))

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        result = generate_panorama(_boundary_covering_center_quarter(), weather=None)

    assert result.status == "ok", result.reason
    scene = trimesh.load(trimesh.util.wrap_as_stream(captured["glb"]), file_type="glb")
    return scene, captured["glb"]


def test_glb_contains_roof_walls_ground_and_panels():
    scene, _ = _generate_scene(_building_insights_with_panels())
    assert set(scene.geometry) == {"Roof", "Walls", "Ground", "SolarPanels"}


def test_glb_reloads_with_trimesh_and_has_real_geometry():
    scene, glb = _generate_scene(_building_insights_with_panels())

    assert glb[:4] == b"glTF"
    for name, mesh in scene.geometry.items():
        assert len(mesh.faces) > 0, f"{name} exported with no faces"
        assert len(mesh.vertices) > 0, f"{name} exported with no vertices"


def test_no_nan_or_inf_coordinates_anywhere_in_the_model():
    scene, _ = _generate_scene(_building_insights_with_panels())
    every_vertex = np.vstack([m.vertices for m in scene.geometry.values()])
    assert np.isfinite(every_vertex).all()


def test_walls_extrude_from_ground_up_to_the_roof():
    scene, _ = _generate_scene()
    walls, roof, ground = scene.geometry["Walls"], scene.geometry["Roof"], scene.geometry["Ground"]

    # Ground is re-based to exactly zero; walls stand on it and reach the roof.
    assert np.allclose(ground.vertices[:, 2], 0.0)
    assert np.isclose(walls.vertices[:, 2].min(), 0.0)
    assert walls.vertices[:, 2].max() > 1.0
    # Wall tops follow the roof surface rather than cutting a flat line.
    assert walls.vertices[:, 2].max() <= roof.vertices[:, 2].max() + 0.01


def test_building_height_is_plausible_not_a_dsm_cliff():
    """The DSM's absolute elevations are ~400 m. If ground re-basing broke,
    the building would export as a 400-metre tower."""
    scene, _ = _generate_scene()
    roof_z = scene.geometry["Roof"].vertices[:, 2]

    assert 0.0 < roof_z.max() < 120.0
    assert roof_z.min() >= 0.0


def test_ground_plane_extends_beyond_the_building():
    scene, _ = _generate_scene()
    ground, walls = scene.geometry["Ground"], scene.geometry["Walls"]

    assert np.ptp(ground.vertices[:, 0]) > np.ptp(walls.vertices[:, 0])
    assert np.ptp(ground.vertices[:, 1]) > np.ptp(walls.vertices[:, 1])
    assert len(ground.faces) == 2  # deliberately lightweight — no invented terrain


def test_panel_count_matches_the_solar_api_layout():
    scene, _ = _generate_scene(_building_insights_with_panels(count=4))
    assert len(scene.geometry["SolarPanels"].faces) // FACES_PER_PANEL == 4


def test_panels_sit_on_the_roof_not_floating_or_buried():
    scene, _ = _generate_scene(_building_insights_with_panels())
    panels, roof = scene.geometry["SolarPanels"], scene.geometry["Roof"]
    clearance = get_panorama_build_params()["panel_clearance_m"]

    for i in range(len(panels.faces) // FACES_PER_PANEL):
        # The module is a frame box followed by a glass slab that sits on
        # top of it, so the module's overall centroid is above its
        # mounting plane. The frame's own centre IS the mounting plane —
        # measure that, or the assertion drifts by half the glass offset.
        start = i * VERTICES_PER_PANEL
        mount = panels.vertices[start : start + 8].mean(axis=0)
        # Read the roof surface the same way generate_panorama() placed the
        # panel — a plain nearest-5-vertex mean is biased near the roof's
        # outline on a sloped surface (asymmetric neighbourhoods), which is
        # not what this test is meant to check.
        roof_below = _nearest_roof_z(roof.vertices, mount[0], mount[1])
        offset = mount[2] - roof_below
        assert offset == pytest.approx(clearance, abs=0.01), "panel left the roof surface"


def test_panel_tilt_and_azimuth_come_from_the_roof_segment():
    """Recovers each panel's surface normal from the exported geometry and
    checks it against the segment's real pitch/azimuth — the placement
    maths, verified through a full export/reload round trip."""
    scene, _ = _generate_scene(_building_insights_with_panels())
    panels = scene.geometry["SolarPanels"]

    largest = panels.area_faces > panels.area_faces.max() * 0.9
    up_facing = panels.face_normals[largest][panels.face_normals[largest][:, 2] > 0]
    normal = up_facing.mean(axis=0)
    normal /= np.linalg.norm(normal)

    tilt = np.degrees(np.arccos(np.clip(normal[2], -1, 1)))
    azimuth = np.degrees(np.arctan2(normal[0], normal[1])) % 360

    assert tilt == pytest.approx(_PANEL_TILT_DEG, abs=0.5)
    assert azimuth == pytest.approx(_PANEL_AZIMUTH_DEG, abs=1.0)


def test_panel_orientation_swaps_the_long_axis():
    portrait = _building_insights_with_panels(count=1)
    landscape = _building_insights_with_panels(count=1)
    landscape["solarPotential"]["solarPanels"][0]["orientation"] = "LANDSCAPE"

    p_scene, _ = _generate_scene(portrait)
    l_scene, _ = _generate_scene(landscape)
    p_extents = p_scene.geometry["SolarPanels"].extents
    l_extents = l_scene.geometry["SolarPanels"].extents

    # Same panel, turned 90 degrees in plan, so the long side swaps axes.
    # The up-slope side is also foreshortened by cos(tilt) in world space —
    # asserting that here checks the tilt is genuinely applied, not just
    # that the extents swapped.
    foreshorten = np.cos(np.radians(_PANEL_TILT_DEG))
    panel_h, panel_w = 1.879, 1.045

    # PORTRAIT: long side runs up the slope (Y), so Y is the foreshortened one.
    assert p_extents[0] == pytest.approx(panel_w, abs=0.05)
    assert p_extents[1] == pytest.approx(panel_h * foreshorten, abs=0.05)
    assert p_extents[1] > p_extents[0]

    # LANDSCAPE: long side runs across the slope (X) at full length.
    assert l_extents[0] == pytest.approx(panel_h, abs=0.05)
    assert l_extents[1] == pytest.approx(panel_w * foreshorten, abs=0.05)
    assert l_extents[0] > l_extents[1]


def test_building_exports_without_panels_when_no_layout_is_available():
    """VIZ-03 degrades in parts: no solarPanels[] means no panels, never an
    invented arrangement — but the real building still ships."""
    scene, _ = _generate_scene({"solarPotential": {"roofSegmentStats": []}})

    assert "SolarPanels" not in scene.geometry
    assert {"Roof", "Walls", "Ground"} <= set(scene.geometry)


def test_no_panels_when_the_response_omits_panel_dimensions():
    insights = _building_insights_with_panels()
    del insights["solarPotential"]["panelHeightMeters"]

    scene, _ = _generate_scene(insights)
    assert "SolarPanels" not in scene.geometry  # never guess a panel size


def test_dsm_nodata_is_not_treated_as_elevation():
    """A nodata sentinel read as a real height puts a several-hundred-metre
    cliff through the roof — the exact bug that made the first real model
    unusable."""
    transform_ = from_bounds(WEST, SOUTH, EAST, NORTH, WIDTH_PX, HEIGHT_PX)
    data = np.full((HEIGHT_PX, WIDTH_PX), 405.0, dtype="float32")
    data[:, : WIDTH_PX // 3] = -9999.0  # a third of the tile is nodata

    with MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            height=HEIGHT_PX,
            width=WIDTH_PX,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=transform_,
            nodata=-9999.0,
        ) as dataset:
            dataset.write(data, 1)
        dsm_bytes = memfile.read()

    vertices, faces, _ = _mesh_from_dsm(dsm_bytes, shape(_boundary_covering_center_quarter()))

    assert len(faces) > 0
    assert np.isfinite(vertices).all()
    assert vertices[:, 2].min() > 0.0  # no -9999 leaked through as a height
    assert np.ptp(vertices[:, 2]) < 1.0  # flat data stays flat, no phantom cliff


def test_mesh_is_built_in_metres_from_a_projected_dsm():
    """The DSM's own CRS is UTM metres, not degrees. Sampled pixels must be
    carried back to lat/lng before the local projection, or every point
    collapses to inf and Delaunay fails."""
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True).transform
    west_m, south_m = to_utm(WEST, SOUTH)
    east_m, north_m = to_utm(EAST, NORTH)
    transform_ = from_bounds(west_m, south_m, east_m, north_m, WIDTH_PX, HEIGHT_PX)
    data = np.tile(np.linspace(400.0, 410.0, WIDTH_PX, dtype="float32"), (HEIGHT_PX, 1))

    with MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            height=HEIGHT_PX,
            width=WIDTH_PX,
            count=1,
            dtype="float32",
            crs="EPSG:32644",
            transform=transform_,
        ) as dataset:
            dataset.write(data, 1)
        dsm_bytes = memfile.read()

    vertices, faces, lnglat = _mesh_from_dsm(dsm_bytes, shape(_boundary_covering_center_quarter()))

    assert len(faces) > 0
    assert np.isfinite(vertices).all()
    # Local metric frame: tens of metres across, never hundreds of thousands
    # of UTM metres and never fractions of a degree.
    assert 1.0 < np.ptp(vertices[:, 0]) < 500.0
    assert 1.0 < np.ptp(vertices[:, 1]) < 500.0
    # And the recovered geographic coordinates land back on the real site.
    lngs = [p[0] for p in lnglat]
    assert WEST - 0.001 < min(lngs) < EAST + 0.001


def test_panorama_url_is_never_empty_when_status_is_ok():
    """CACHE/VIZ-02 contract: an ok result always carries a usable URL, so
    the frontend never renders a viewer pointed at nothing."""
    captured = {}

    def _capture(data, key):
        captured["key"] = key
        return f"http://localhost:8000/artifacts/{key}"

    with (
        _patch_dsm_fetch(_make_synthetic_dsm()),
        patch("solarfit.providers.storage.upload_glb", side_effect=_capture),
    ):
        result = generate_panorama(_boundary_covering_center_quarter(), weather=None)

    assert result.status == "ok"
    assert result.url
    assert result.url.endswith(".glb")
    assert captured["key"].startswith("panorama/")


def test_building_insights_failure_still_exports_the_building():
    """Panels and shading both come from Building Insights. Losing it must
    cost the panels, not the whole model."""
    with (
        _patch_dsm_fetch(_make_synthetic_dsm()),
        patch(
            "solarfit.providers.vision.fetch_building_insights",
            side_effect=RuntimeError("network down"),
        ),
        patch("solarfit.providers.storage.upload_glb", return_value="https://x/y.glb") as upload,
    ):
        result = generate_panorama(_boundary_covering_center_quarter(), weather=None)

    assert result.status == "ok"
    scene = trimesh.load(trimesh.util.wrap_as_stream(upload.call_args[0][0]), file_type="glb")
    assert {"Roof", "Walls", "Ground"} <= set(scene.geometry)
    assert "SolarPanels" not in scene.geometry


def test_missing_ground_estimate_falls_back_to_a_configured_height():
    """A DSM that yields no usable ground pixels must not produce a
    zero-height or negative building."""
    fallback = get_panorama_build_params()["fallback_building_height_m"]

    with (
        _patch_dsm_fetch(_make_synthetic_dsm()),
        patch("solarfit.engine.panorama._ground_elevation", return_value=None),
        patch("solarfit.providers.storage.upload_glb", return_value="https://x/y.glb") as upload,
    ):
        result = generate_panorama(_boundary_covering_center_quarter(), weather=None)

    assert result.status == "ok"
    scene = trimesh.load(trimesh.util.wrap_as_stream(upload.call_args[0][0]), file_type="glb")
    roof_z = scene.geometry["Roof"].vertices[:, 2]
    assert np.median(roof_z) == pytest.approx(fallback, abs=0.01)


def test_absurd_ground_estimate_is_rejected_for_the_fallback():
    """VIZ-03. A DSM artifact must degrade to the configured height, never
    export as a hundred-metre cliff."""
    params = get_panorama_build_params()

    with (
        _patch_dsm_fetch(_make_synthetic_dsm()),
        patch("solarfit.engine.panorama._ground_elevation", return_value=-5000.0),
        patch("solarfit.providers.storage.upload_glb", return_value="https://x/y.glb") as upload,
    ):
        result = generate_panorama(_boundary_covering_center_quarter(), weather=None)

    assert result.status == "ok"
    scene = trimesh.load(trimesh.util.wrap_as_stream(upload.call_args[0][0]), file_type="glb")
    roof_z = scene.geometry["Roof"].vertices[:, 2]
    assert np.median(roof_z) == pytest.approx(params["fallback_building_height_m"], abs=0.01)
    assert roof_z.max() < params["max_building_height_m"]
