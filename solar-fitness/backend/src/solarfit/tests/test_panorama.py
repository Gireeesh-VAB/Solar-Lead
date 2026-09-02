"""§16 Testing — Day 4 implementation of §9.12 3D Visualization
(VIZ-01..05).

_mesh_from_dsm() is exercised against a real synthetic in-memory DSM
GeoTIFF with a known geotransform — an integration test of the actual
rasterio crop + triangulation + trimesh export, not a mock.
generate_panorama() mocks providers.vision's Solar API calls and
providers.storage.upload_glb — no live network calls in the automated
suite.
"""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import trimesh
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from shapely.geometry import shape

from solarfit.engine.panorama import (
    FACES_PER_PANEL,
    VERTICES_PER_PANEL,
    _boundary_version_hash,
    _mesh_from_dsm,
    _vertex_colors_from_segments,
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
        d2 = (roof.vertices[:, 0] - mount[0]) ** 2 + (roof.vertices[:, 1] - mount[1]) ** 2
        roof_below = roof.vertices[np.argsort(d2)[:5], 2].mean()
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
