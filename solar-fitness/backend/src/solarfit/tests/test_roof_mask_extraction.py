"""§16 Testing — GEO-04's real-outline upgrade: vectorising the Solar
API's own building-mask raster into a roof polygon instead of storing
the boundingBox rectangle (providers/solar_api.py::
extract_roof_polygon_from_mask / _vectorize_building_mask), plus the
building-confidence signal riding along with it: MaskVectorization.
competing_regions, the count of OTHER disconnected mask regions near the
pin besides whichever one was selected.

Synthetic in-memory GeoTIFFs with a known, projected (metric) transform
— same integration-test discipline as test_vision.py's
crop_to_boundary() tests, not a mock of rasterio itself. The masks here
match the real Solar API mask's own shape: single-band uint8, values
{0, 1}, already in a projected CRS (EPSG:32644 — Hyderabad's UTM zone).
"""

import numpy as np
import pytest
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import shape
from shapely.ops import transform as shapely_transform

from solarfit.providers.solar_api import (
    _vectorize_building_mask,
    extract_roof_polygon_from_mask,
    polygon_centroid,
)

# A metric origin near Hyderabad (arbitrary — only its WGS84 round-trip
# matters), with 0.5m pixels: coarser than Google's real 0.1m masks, but
# still fine-grained enough to make small/large regions unambiguous while
# keeping the arrays tiny.
_ORIGIN_X, _ORIGIN_Y = 500_000.0, 1_921_000.0
_PIXEL_M = 0.5
_CRS = "EPSG:32644"

_to_wgs84 = Transformer.from_crs(_CRS, "EPSG:4326", always_xy=True).transform
_to_metric = Transformer.from_crs("EPSG:4326", _CRS, always_xy=True).transform


def _pixel_center_wgs84(row: int, col: int) -> tuple[float, float]:
    """The (lat, lng) of one pixel's centre, for use as a query point."""
    x = _ORIGIN_X + (col + 0.5) * _PIXEL_M
    y = _ORIGIN_Y - (row + 0.5) * _PIXEL_M
    lng, lat = _to_wgs84(x, y)
    return lat, lng


def _make_mask_geotiff(band: np.ndarray) -> bytes:
    height, width = band.shape
    transform = from_origin(_ORIGIN_X, _ORIGIN_Y, _PIXEL_M, _PIXEL_M)
    with MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype="uint8",
            crs=_CRS,
            transform=transform,
        ) as dataset:
            dataset.write(band, 1)
        return memfile.read()


def _square_mask(size: int = 100, *, square_slice=(slice(20, 60), slice(20, 60))) -> np.ndarray:
    """A size x size mask with one filled square region — big enough
    (40 x 0.5m = 20m per side, 400 m2) to clear the noise-region filter."""
    band = np.zeros((size, size), dtype="uint8")
    band[square_slice] = 1
    return band


# ---------------------------------------------------------------------------
# _vectorize_building_mask — the core raster -> polygon logic
# ---------------------------------------------------------------------------


def test_a_clean_square_region_vectorises_to_a_real_polygon():
    band = _square_mask()
    lat, lng = _pixel_center_wgs84(40, 40)  # dead centre of the filled square

    result = _vectorize_building_mask(_make_mask_geotiff(band), lat, lng)

    assert result.polygon is not None
    assert result.polygon["type"] == "Polygon"
    assert result.competing_regions == 0  # only one region in this mask at all
    poly = shape(result.polygon)
    assert poly.is_valid
    metric = shapely_transform(_to_metric, poly)
    # 40 x 40 pixels @ 0.5m = 20m x 20m = 400 m2, give or take simplification.
    assert metric.area == pytest.approx(400.0, rel=0.05)


def test_an_all_zero_mask_returns_none():
    band = np.zeros((50, 50), dtype="uint8")
    lat, lng = _pixel_center_wgs84(25, 25)

    result = _vectorize_building_mask(_make_mask_geotiff(band), lat, lng)

    assert result.polygon is None
    assert result.competing_regions == 0


def test_a_noise_sized_speck_is_dropped_not_returned_as_a_building():
    """A single stray pixel (0.5m x 0.5m = 0.25 m2) is well below any
    real roof — must never be handed back as "the building"."""
    band = np.zeros((50, 50), dtype="uint8")
    band[25, 25] = 1
    lat, lng = _pixel_center_wgs84(25, 25)

    result = _vectorize_building_mask(_make_mask_geotiff(band), lat, lng)

    assert result.polygon is None


def test_the_region_containing_the_pin_is_selected_over_a_bigger_neighbour():
    """The whole point of Phase 2's region-selection logic: a query
    radius can catch more than one building, and the pin decides which
    one is "the" roof — never just the largest blob in frame."""
    band = np.zeros((100, 100), dtype="uint8")
    # A small region the pin sits inside...
    band[10:20, 10:20] = 1  # 10x10 px = 5m x 5m = 25 m2
    # ...and a much bigger, disconnected region elsewhere in the same tile.
    band[60:95, 60:95] = 1  # 35x35 px = 17.5m x 17.5m = ~306 m2
    lat, lng = _pixel_center_wgs84(15, 15)  # inside the SMALL region

    result = _vectorize_building_mask(_make_mask_geotiff(band), lat, lng)

    assert result.polygon is not None
    poly = shape(result.polygon)
    metric = shapely_transform(_to_metric, poly)
    assert metric.area == pytest.approx(25.0, rel=0.1)  # the small region, not the big one
    # The other, bigger region is exactly the "competing building" signal
    # this count exists for — a real one, right there in the same mask.
    assert result.competing_regions == 1


def test_a_pin_just_outside_the_region_still_matches_it():
    """A pin landing a metre or two off the true roof edge is ordinary —
    ~1m away, well inside the configured max_pin_distance_m margin."""
    band = _square_mask()  # filled 20m x 20m square, rows/cols 20:60
    lat, lng = _pixel_center_wgs84(10, 40)  # ~5m above the square's top edge

    result = _vectorize_building_mask(_make_mask_geotiff(band), lat, lng)

    assert result.polygon is not None


def test_a_pin_far_from_every_region_returns_none():
    """Nothing in the mask is trusted to be the intended building when
    the pin is nowhere near any of it — extraction reports "no match"
    rather than silently returning an unrelated roof."""
    band = _square_mask()
    lat, lng = _pixel_center_wgs84(99, 5)  # far corner, well past the margin

    result = _vectorize_building_mask(_make_mask_geotiff(band), lat, lng)

    assert result.polygon is None
    # The (unreachable) region is still real evidence a building exists
    # nearby, even though it wasn't close enough to trust as "the" one.
    assert result.competing_regions == 1


def test_the_result_has_more_than_four_vertices():
    """Distinguishing evidence that this is a real traced-ish outline,
    not another bounding rectangle in disguise."""
    band = np.zeros((100, 100), dtype="uint8")
    # An L-shape, not a rectangle.
    band[20:60, 20:40] = 1
    band[40:60, 20:70] = 1
    lat, lng = _pixel_center_wgs84(50, 50)

    result = _vectorize_building_mask(_make_mask_geotiff(band), lat, lng)

    assert result.polygon is not None
    assert len(result.polygon["coordinates"][0]) > 5


# ---------------------------------------------------------------------------
# polygon_centroid — must always describe the boundary passed in, never a
# stale centroid left over from some other, previously-resolved boundary
# ---------------------------------------------------------------------------


def test_polygon_centroid_matches_a_known_square():
    square = {
        "type": "Polygon",
        "coordinates": [[[78.480, 17.380], [78.482, 17.380], [78.482, 17.382], [78.480, 17.382], [78.480, 17.380]]],
    }
    centroid = polygon_centroid(square)
    assert centroid == {"type": "Point", "coordinates": [pytest.approx(78.481), pytest.approx(17.381)]}


def test_polygon_centroid_tracks_whichever_polygon_it_is_given():
    """Two disjoint polygons must produce two clearly different
    centroids — the regression this guards against is a caller reusing
    ONE polygon's centroid after swapping in a completely different
    polygon as the boundary."""
    near = {
        "type": "Polygon",
        "coordinates": [[[78.480, 17.380], [78.481, 17.380], [78.481, 17.381], [78.480, 17.381], [78.480, 17.380]]],
    }
    far = {
        "type": "Polygon",
        "coordinates": [[[78.510, 17.400], [78.511, 17.400], [78.511, 17.401], [78.510, 17.401], [78.510, 17.400]]],
    }
    assert polygon_centroid(near) != polygon_centroid(far)


def test_polygon_centroid_returns_none_for_garbage_input():
    assert polygon_centroid({}) is None
    assert polygon_centroid({"type": "Polygon", "coordinates": []}) is None


# ---------------------------------------------------------------------------
# extract_roof_polygon_from_mask — the full path, network mocked
# ---------------------------------------------------------------------------


def test_no_mask_url_in_the_data_layers_response_returns_none(monkeypatch):
    import solarfit.providers.vision as vision_module

    monkeypatch.setattr(vision_module, "fetch_solar_api_datalayers", lambda lat, lng, r: {})

    result = extract_roof_polygon_from_mask(17.385, 78.4867)
    assert result.polygon is None
    assert result.competing_regions == 0


def test_a_download_failure_degrades_to_none_not_an_exception(monkeypatch):
    import solarfit.providers.vision as vision_module

    monkeypatch.setattr(
        vision_module,
        "fetch_solar_api_datalayers",
        lambda lat, lng, r: {"maskUrl": "https://example.invalid/mask"},
    )

    def _boom(url):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(vision_module, "_download_geotiff_bytes", _boom)

    result = extract_roof_polygon_from_mask(17.385, 78.4867)
    assert result.polygon is None


def test_a_real_mask_response_is_vectorised_end_to_end(monkeypatch):
    import solarfit.providers.vision as vision_module

    band = _square_mask()
    mask_bytes = _make_mask_geotiff(band)
    lat, lng = _pixel_center_wgs84(40, 40)

    monkeypatch.setattr(
        vision_module,
        "fetch_solar_api_datalayers",
        lambda q, w, r: {"maskUrl": "https://example.invalid/mask"},
    )
    monkeypatch.setattr(vision_module, "_download_geotiff_bytes", lambda url: mask_bytes)

    result = extract_roof_polygon_from_mask(lat, lng)

    assert result.polygon is not None
    assert result.polygon["type"] == "Polygon"
    assert result.competing_regions == 0
