"""§16 Testing — 'Vision refinement' row, Day 2/3 implementation of
§9.11 Vision Refinement (VIS-01..06) and §9.16 Obstacle Detection's
detection half (OBS-01..03).

crop_to_boundary() is tested against a real synthetic in-memory GeoTIFF
with a known geotransform — an integration test of the actual
rasterio/GDAL masking logic, not a mock. refine_with_vision_model() is
tested against a mocked OpenAI client — no live API calls in the
automated suite (see manual_smoke_test_vision.py for the one live
call, gated on real credentials).
"""

from unittest.mock import MagicMock, patch

import httpx
import numpy as np
import pytest
from affine import Affine
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds

from solarfit.domain.assessment import Obstacle
from solarfit.packs.config_pack import get_vision_min_confidence
from solarfit.providers.vision import (
    CroppedImagery,
    _ObstacleSchema,
    _VisionRefinementSchema,
    crop_to_boundary,
    fetch_solar_api_datalayers,
    refine_with_vision_model,
    validate_obstacle_polygon,
)

# A small area around Hyderabad, matching test_projection.py's reference point.
WEST, SOUTH, EAST, NORTH = 78.4860, 17.3845, 78.4874, 17.3855
WIDTH_PX, HEIGHT_PX = 100, 100


def _make_synthetic_geotiff() -> bytes:
    """A 3-band uint8 GeoTIFF covering WEST/SOUTH/EAST/NORTH, with a
    distinct constant colour so we can assert the crop actually
    extracted real pixel data, not an empty/black image."""
    transform = from_bounds(WEST, SOUTH, EAST, NORTH, WIDTH_PX, HEIGHT_PX)
    data = np.full((3, HEIGHT_PX, WIDTH_PX), fill_value=200, dtype="uint8")

    with MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            height=HEIGHT_PX,
            width=WIDTH_PX,
            count=3,
            dtype="uint8",
            crs="EPSG:4326",
            transform=transform,
        ) as dataset:
            dataset.write(data)
        return memfile.read()


def _boundary_covering_center_quarter() -> dict:
    """A polygon covering roughly the middle quarter of the synthetic
    image's extent — small enough that crop must actually shrink the
    image, not just return the whole thing."""
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


def test_crop_to_boundary_returns_valid_smaller_png():
    imagery = _make_synthetic_geotiff()
    boundary = _boundary_covering_center_quarter()

    cropped = crop_to_boundary(imagery, boundary)

    assert cropped.png_bytes[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes — a real, valid PNG
    assert cropped.crs is not None
    assert cropped.transform is not None
    # Cropped to ~half the width/height (quarter-extent boundary), not the full 100x100.
    assert cropped.width < WIDTH_PX
    assert cropped.height < HEIGHT_PX

    with MemoryFile(cropped.png_bytes) as memfile, memfile.open() as dataset:
        assert dataset.count == 3
        assert dataset.width == cropped.width
        assert dataset.height == cropped.height
        pixels = dataset.read()
        assert pixels.max() > 0  # real pixel data extracted, not an empty crop


def test_crop_to_boundary_full_extent_matches_source_size():
    imagery = _make_synthetic_geotiff()
    full_boundary = {
        "type": "Polygon",
        "coordinates": [[[WEST, SOUTH], [EAST, SOUTH], [EAST, NORTH], [WEST, NORTH], [WEST, SOUTH]]],
    }

    cropped = crop_to_boundary(imagery, full_boundary)

    assert abs(cropped.width - WIDTH_PX) <= 1
    assert abs(cropped.height - HEIGHT_PX) <= 1


def test_crop_to_boundary_transform_recovers_known_corner():
    imagery = _make_synthetic_geotiff()
    boundary = _boundary_covering_center_quarter()

    cropped = crop_to_boundary(imagery, boundary)
    top_left_lng, top_left_lat = cropped.transform * (0, 0)

    # The crop's top-left pixel-corner must land within the source
    # image's overall extent — proves the transform's direction/sign is
    # right, not just that *some* transform came back.
    assert WEST <= top_left_lng <= EAST
    assert SOUTH <= top_left_lat <= NORTH


def _fake_cropped_imagery() -> CroppedImagery:
    """A minimal CroppedImagery for tests that don't need a real crop —
    identity transform in EPSG:4326, so pixel fractions map 1:1 to
    lng/lat degrees (not realistic geography, but exercises the math)."""
    return CroppedImagery(
        png_bytes=b"fake-png-bytes",
        transform=Affine.identity(),
        crs=CRS.from_epsg(4326),
        width=10,
        height=10,
    )


def _mock_completion(obstruction_notes: list[str], confidence: float, obstacles: list[_ObstacleSchema] | None = None):
    parsed = _VisionRefinementSchema(
        obstruction_notes=obstruction_notes, confidence=confidence, obstacles=obstacles or []
    )
    message = MagicMock(parsed=parsed)
    choice = MagicMock(message=message)
    return MagicMock(choices=[choice])


def test_refine_with_vision_model_success():
    with patch("solarfit.providers.vision.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.parse.return_value = _mock_completion(
            ["water tank near the north edge"], confidence=0.9
        )
        mock_openai_cls.return_value = mock_client

        result = refine_with_vision_model(_fake_cropped_imagery(), boundary={})

    assert result.status == "ok"
    assert result.confidence == 0.9
    assert "water tank near the north edge" in result.obstruction_notes
    assert result.corrected_boundary is None  # VIS-02 scoping note
    assert result.obstacles == []  # no obstacles reported by the mock in this test


def test_refine_with_vision_model_low_confidence_is_insufficient_data():
    below_threshold = get_vision_min_confidence() - 0.01
    with patch("solarfit.providers.vision.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.parse.return_value = _mock_completion([], confidence=below_threshold)
        mock_openai_cls.return_value = mock_client

        result = refine_with_vision_model(_fake_cropped_imagery(), boundary={})

    assert result.status == "insufficient_data"  # VIS-04
    assert result.obstacles == []  # never trust obstacle boxes from a low-confidence read


def test_refine_with_vision_model_call_failure_is_insufficient_data():
    with patch("solarfit.providers.vision.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.parse.side_effect = RuntimeError("simulated API failure")
        mock_openai_cls.return_value = mock_client

        result = refine_with_vision_model(_fake_cropped_imagery(), boundary={})

    assert result.status == "insufficient_data"  # VIS-04: never raises, never blocks the pipeline
    assert result.obstacles == []


def test_refine_with_vision_model_converts_obstacle_bboxes_to_geojson():
    imagery = _make_synthetic_geotiff()
    full_boundary = {
        "type": "Polygon",
        "coordinates": [[[WEST, SOUTH], [EAST, SOUTH], [EAST, NORTH], [WEST, NORTH], [WEST, SOUTH]]],
    }
    cropped = crop_to_boundary(imagery, full_boundary)

    bbox = _ObstacleSchema(type="water_tank", x_min=0.1, y_min=0.1, x_max=0.3, y_max=0.3, confidence=0.95)
    with patch("solarfit.providers.vision.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.parse.return_value = _mock_completion(
            ["a rooftop water tank"], confidence=0.9, obstacles=[bbox]
        )
        mock_openai_cls.return_value = mock_client

        result = refine_with_vision_model(cropped, boundary=full_boundary)

    assert len(result.obstacles) == 1
    obstacle = result.obstacles[0]
    assert obstacle.type == "water_tank"
    assert obstacle.confidence == 0.95
    assert obstacle.applied is False
    assert isinstance(obstacle.id, str) and obstacle.id

    ring = obstacle.bounding_polygon["coordinates"][0]
    assert len(ring) == 5  # closed ring: 4 corners + repeated first point
    assert ring[0] == ring[-1]
    for lng, lat in ring:
        assert WEST <= lng <= EAST
        assert SOUTH <= lat <= NORTH


def test_refine_with_vision_model_drops_degenerate_bbox_obstacle():
    bbox = _ObstacleSchema(type="hvac_unit", x_min=0.5, y_min=0.2, x_max=0.5, y_max=0.4, confidence=0.9)
    with patch("solarfit.providers.vision.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.parse.return_value = _mock_completion([], confidence=0.9, obstacles=[bbox])
        mock_openai_cls.return_value = mock_client

        result = refine_with_vision_model(_fake_cropped_imagery(), boundary={})

    assert result.obstacles == []


def _square_boundary(west, south, east, north) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
    }


def _obstacle_at(west, south, east, north, confidence=0.9, obstacle_type="water_tank") -> Obstacle:
    return Obstacle(
        type=obstacle_type,
        bounding_polygon=_square_boundary(west, south, east, north),
        confidence=confidence,
    )


def test_validate_obstacle_polygon_accepts_polygon_within_boundary():
    boundary = _square_boundary(78.4860, 17.3845, 78.4874, 17.3855)
    obstacle = _obstacle_at(78.4862, 17.3847, 78.4864, 17.3849)

    assert validate_obstacle_polygon(obstacle, boundary) is True


def test_validate_obstacle_polygon_rejects_self_intersecting_polygon():
    boundary = _square_boundary(78.4860, 17.3845, 78.4874, 17.3855)
    bowtie = Obstacle(
        type="hvac_unit",
        confidence=0.9,
        bounding_polygon={
            "type": "Polygon",
            "coordinates": [
                [
                    [78.4862, 17.3847],
                    [78.4864, 17.3849],
                    [78.4862, 17.3849],
                    [78.4864, 17.3847],
                    [78.4862, 17.3847],
                ]
            ],
        },
    )

    assert validate_obstacle_polygon(bowtie, boundary) is False


def test_validate_obstacle_polygon_rejects_fewer_than_3_vertices():
    boundary = _square_boundary(78.4860, 17.3845, 78.4874, 17.3855)
    degenerate = Obstacle(
        type="vent",
        confidence=0.9,
        bounding_polygon={
            "type": "Polygon",
            "coordinates": [[[78.4862, 17.3847], [78.4864, 17.3849], [78.4862, 17.3847]]],
        },
    )

    assert validate_obstacle_polygon(degenerate, boundary) is False


def test_validate_obstacle_polygon_rejects_polygon_outside_boundary():
    boundary = _square_boundary(78.4860, 17.3845, 78.4874, 17.3855)
    outside = _obstacle_at(78.5000, 17.4000, 78.5002, 17.4002)

    assert validate_obstacle_polygon(outside, boundary) is False


def test_validate_obstacle_polygon_rejects_implausibly_large_area():
    boundary = _square_boundary(78.4860, 17.3845, 78.4874, 17.3855)
    # Nearly the full boundary extent — comfortably over the 50% cap.
    too_large = _obstacle_at(78.4860, 17.3845, 78.4874, 17.3855)

    assert validate_obstacle_polygon(too_large, boundary) is False


def test_validate_obstacle_polygon_rejects_implausibly_small_area():
    boundary = _square_boundary(78.4860, 17.3845, 78.4874, 17.3855)
    # A sliver well under 0.25 m^2.
    tiny = _obstacle_at(78.48620, 17.38470, 78.486201, 17.384701)

    assert validate_obstacle_polygon(tiny, boundary) is False


def _mock_httpx_response(status_code: int, json_data: dict | None = None) -> httpx.Response:
    request = httpx.Request("GET", "https://solar.googleapis.com/v1/dataLayers:get")
    return httpx.Response(status_code, request=request, json=json_data)


def _mock_httpx_client(*side_effects) -> MagicMock:
    client = MagicMock()
    client.get.side_effect = list(side_effects)
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    return client


def test_fetch_solar_api_datalayers_retries_on_5xx_then_succeeds():
    mock_client = _mock_httpx_client(
        _mock_httpx_response(503),
        _mock_httpx_response(200, json_data={"rgbUrl": "https://example.com/rgb.tif"}),
    )

    with (
        patch("solarfit.providers.vision.httpx.Client", return_value=mock_client),
        patch("solarfit.providers.vision.time.sleep"),
    ):
        result = fetch_solar_api_datalayers(17.385, 78.4867)

    assert result == {"rgbUrl": "https://example.com/rgb.tif"}
    assert mock_client.get.call_count == 2


def test_fetch_solar_api_datalayers_retries_on_timeout_then_succeeds():
    mock_client = _mock_httpx_client(
        httpx.TimeoutException("timed out"),
        _mock_httpx_response(200, json_data={"dsmUrl": "https://example.com/dsm.tif"}),
    )

    with (
        patch("solarfit.providers.vision.httpx.Client", return_value=mock_client),
        patch("solarfit.providers.vision.time.sleep"),
    ):
        result = fetch_solar_api_datalayers(17.385, 78.4867)

    assert result == {"dsmUrl": "https://example.com/dsm.tif"}
    assert mock_client.get.call_count == 2


def test_fetch_solar_api_datalayers_never_retries_a_4xx():
    mock_client = _mock_httpx_client(_mock_httpx_response(403))

    with (
        patch("solarfit.providers.vision.httpx.Client", return_value=mock_client),
        patch("solarfit.providers.vision.time.sleep") as sleep,
        pytest.raises(httpx.HTTPStatusError),
    ):
        fetch_solar_api_datalayers(17.385, 78.4867)

    assert mock_client.get.call_count == 1  # a bad API key doesn't fix itself on retry
    sleep.assert_not_called()
