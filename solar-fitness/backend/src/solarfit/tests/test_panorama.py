"""§16 Testing — Day 4 implementation of §9.12 3D Visualization
(VIZ-01..05).

_mesh_from_dsm() is exercised against a real synthetic in-memory DSM
GeoTIFF with a known geotransform — an integration test of the actual
rasterio crop + triangulation + trimesh export, not a mock.
generate_panorama() mocks providers.vision's Solar API calls and
providers.storage.upload_glb — no live network calls in the automated
suite.
"""

from unittest.mock import MagicMock, patch

import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds

from solarfit.engine.panorama import (
    _boundary_version_hash,
    _vertex_colors_from_segments,
    generate_panorama,
)

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
        fetch_solar_api_datalayers=MagicMock(return_value={"dsmUrl": "https://example.com/dsm.tif"}),
        _download_geotiff_bytes=MagicMock(return_value=dsm_bytes),
        fetch_building_insights=MagicMock(return_value={}),
    )


def test_generate_panorama_produces_real_glb_and_uploads():
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()

    with (
        _patch_dsm_fetch(dsm_bytes),
        patch(
            "solarfit.providers.storage.upload_glb", return_value="https://storage.example.com/p/x.glb"
        ) as upload,
    ):
        result = generate_panorama(boundary, weather=None)

    assert result.status == "ok"
    assert result.url == "https://storage.example.com/p/x.glb"
    assert result.version == _boundary_version_hash(boundary)
    assert result.generated_at is not None

    upload.assert_called_once()
    glb_bytes = upload.call_args[0][0]
    assert glb_bytes[:4] == b"glTF"  # a real, valid glTF-binary export, not a fabricated placeholder


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
    assert _vertex_colors_from_segments([(78.4864, 17.3850)], {"solarPotential": {"roofSegmentStats": []}}) is None


def test_generate_panorama_applies_shading_tint_without_affecting_result():
    boundary = _boundary_covering_center_quarter()
    dsm_bytes = _make_synthetic_dsm()
    building_insights = {"solarPotential": {"roofSegmentStats": [_BRIGHT_SEGMENT, _DARK_SEGMENT]}}

    with (
        _patch_dsm_fetch(dsm_bytes),
        patch("solarfit.providers.vision.fetch_building_insights", return_value=building_insights),
        patch(
            "solarfit.providers.storage.upload_glb", return_value="https://storage.example.com/p/x.glb"
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
        patch("solarfit.providers.vision.fetch_building_insights", side_effect=RuntimeError("network down")),
        patch("solarfit.providers.storage.upload_glb", return_value="https://storage.example.com/p/x.glb"),
    ):
        result = generate_panorama(boundary, weather=None)

    assert result.status == "ok"  # a shading-tint failure must never fail the whole panorama (VIZ-03)
