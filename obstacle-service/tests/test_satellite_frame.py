"""The Google satellite frame the models are shown. No network: the tile download is replaced by a blank image."""
import pytest
from PIL import Image
from pyproj import Transformer
from shapely.geometry import box, mapping, shape

from obstacle_service import satellite_frame
from obstacle_service.satellite_frame import fetch_roof_frame, frame_for_roof, pick_zoom

_TO_MERCATOR = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
_LNG, _LAT, _SPAN = 78.4867, 17.385, 0.00023  # a ~25 m x 25 m roof in Hyderabad
_ROOF = mapping(box(_LNG, _LAT, _LNG + _SPAN, _LAT + _SPAN))


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(satellite_frame, "_download_tile", lambda lat, lng, zoom, key: Image.new("RGB", (640, 640), (120, 120, 120)))


def test_zoom_fits_the_roof_and_never_exceeds_the_cap():
    assert pick_zoom(17.4, 40) == 19  # a small roof would ask for 21; capped at 19
    assert pick_zoom(17.4, 40, max_zoom=21) >= 20
    assert pick_zoom(17.4, 600) < 19  # a big roof needs a wider view
    assert pick_zoom(17.4, 1_000_000) == 15  # and never below 15


def test_frame_is_centred_on_the_roof():
    lat, lng, zoom = frame_for_roof(_ROOF)
    assert lat == pytest.approx(_LAT + _SPAN / 2) and lng == pytest.approx(_LNG + _SPAN / 2) and zoom == 19


def test_no_key_or_no_boundary_means_no_frame():
    assert fetch_roof_frame(_ROOF, "") is None
    assert fetch_roof_frame({}, "key") is None


def test_a_failed_download_degrades_to_no_frame(monkeypatch):
    monkeypatch.setattr(satellite_frame, "_download_tile", lambda *a: None)
    assert fetch_roof_frame(_ROOF, "key") is None


def test_the_roof_fills_the_frame_with_room_to_spare_and_pixels_map_back_to_it():
    frame = fetch_roof_frame(_ROOF, "key")
    assert frame is not None and frame.epsg == 3857
    assert 560 <= max(frame.width, frame.height) <= 660  # enlarged so the roof's longest side is ~640 px / 1.6
    inverse = ~frame.transform
    xs, ys = zip(*[inverse * _TO_MERCATOR(x, y) for x, y in shape(_ROOF).exterior.coords], strict=True)
    assert min(xs) > 0 and min(ys) > 0 and max(xs) < frame.width and max(ys) < frame.height  # the whole roof is inside the picture
    assert min(xs) == pytest.approx(frame.width - max(xs), abs=6)  # equal margins each side
    assert min(ys) == pytest.approx(frame.height - max(ys), abs=6)


def test_with_no_crop_margin_the_whole_tile_is_used():
    frame = fetch_roof_frame(_ROOF, "key", crop_margin=0)
    assert (frame.width, frame.height) == (640, 640)


def test_a_download_error_never_leaks_the_key_into_the_log(monkeypatch, caplog):
    import httpx

    def _boom(*a, **k):
        raise httpx.ConnectError("https://maps.googleapis.com/maps/api/staticmap?key=SECRET-KEY-VALUE")

    monkeypatch.undo()  # use the real _download_tile, with the network call failing
    monkeypatch.setattr(httpx, "get", _boom)
    with caplog.at_level("WARNING"):
        assert satellite_frame._download_tile(17.0, 78.0, 19, "SECRET-KEY-VALUE") is None
    assert "SECRET-KEY-VALUE" not in caplog.text
