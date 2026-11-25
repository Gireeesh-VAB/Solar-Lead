"""providers/satellite_frame.py - the Google satellite frame the obstacle
models are shown - and how the YOLO ensemble chooses between it and the
Solar API crop. No network: the tile download is replaced by a blank image."""

import pytest
from PIL import Image
from pyproj import Transformer
from shapely.geometry import box, mapping, shape

from solarfit.config import get_settings
from solarfit.providers import satellite_frame
from solarfit.providers import yolo_obstacle_detector as yolo_module
from solarfit.providers.satellite_frame import fetch_roof_frame, frame_for_roof, pick_zoom
from solarfit.providers.yolo_obstacle_detector import YoloEnsembleDetector, _mostly_on_roof

_TO_MERCATOR = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
# A ~25 m x 25 m roof in Hyderabad.
_LNG, _LAT, _SPAN = 78.4867, 17.385, 0.00023
_ROOF = mapping(box(_LNG, _LAT, _LNG + _SPAN, _LAT + _SPAN))


@pytest.fixture(autouse=True)
def _no_network_no_keys(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "google_maps_api_key", "")
    monkeypatch.setattr(settings, "google_solar_api_key", "")
    monkeypatch.setattr(
        satellite_frame,
        "_download_tile",
        lambda lat, lng, zoom, key: Image.new("RGB", (640, 640), (120, 120, 120)),
    )


def test_zoom_fits_the_roof_and_never_exceeds_the_cap():
    assert pick_zoom(17.4, 40) == 19  # a small roof would ask for 21; capped at 19
    assert pick_zoom(17.4, 40, max_zoom=21) >= 20
    assert pick_zoom(17.4, 600) < 19  # a big roof needs a wider view
    assert pick_zoom(17.4, 1_000_000) == 15  # and never below 15


def test_frame_is_centred_on_the_roof():
    lat, lng, zoom = frame_for_roof(_ROOF)

    assert lat == pytest.approx(_LAT + _SPAN / 2)
    assert lng == pytest.approx(_LNG + _SPAN / 2)
    assert zoom == 19


def test_no_key_or_no_boundary_means_no_frame():
    assert fetch_roof_frame(_ROOF, "") is None
    assert fetch_roof_frame({}, "key") is None


def test_a_failed_download_degrades_to_no_frame(monkeypatch):
    monkeypatch.setattr(satellite_frame, "_download_tile", lambda *a: None)

    assert fetch_roof_frame(_ROOF, "key") is None


def test_the_roof_fills_the_frame_with_room_to_spare_and_pixels_map_back_to_it():
    frame = fetch_roof_frame(_ROOF, "key")

    assert frame is not None and frame.crs.to_epsg() == 3857
    # Enlarged so the roof's longest side is ~640 px / 1.6 (30 % margin each side).
    assert 560 <= max(frame.width, frame.height) <= 660
    inverse = ~frame.transform
    xs, ys = zip(*[inverse * _TO_MERCATOR(x, y) for x, y in shape(_ROOF).exterior.coords], strict=True)
    # The whole roof lies inside the picture ...
    assert min(xs) > 0 and min(ys) > 0 and max(xs) < frame.width and max(ys) < frame.height
    # ... occupying ~1/1.6 of the longer side, centred (equal margins each side).
    assert (max(xs) - min(xs)) / frame.width == pytest.approx(1 / 1.6, abs=0.06) or (
        (max(ys) - min(ys)) / frame.height == pytest.approx(1 / 1.6, abs=0.06)
    )
    assert min(xs) == pytest.approx(frame.width - max(xs), abs=6)
    assert min(ys) == pytest.approx(frame.height - max(ys), abs=6)


def test_with_no_crop_margin_the_whole_tile_is_used():
    frame = fetch_roof_frame(_ROOF, "key", crop_margin=0)

    assert (frame.width, frame.height) == (640, 640)


# --- how the ensemble picks its imagery --------------------------------------


def test_the_ensemble_brings_its_own_imagery_only_when_a_maps_key_exists(monkeypatch):
    detector = YoloEnsembleDetector([])
    assert detector.needs_solar_imagery is True  # no key -> Solar crop

    monkeypatch.setattr(get_settings(), "google_maps_api_key", "key")
    assert detector.needs_solar_imagery is False


def test_with_no_imagery_at_all_the_ensemble_reports_nothing(monkeypatch, tmp_path):
    detector = YoloEnsembleDetector([tmp_path / "a.pt"])

    def _no_imagery(lat, lng):
        raise ValueError("no imagery here")

    monkeypatch.setattr(yolo_module, "fetch_rgb_imagery", _no_imagery)

    assert detector.detect(None, _ROOF) == []


def test_when_the_satellite_frame_fails_the_ensemble_falls_back_to_the_solar_crop(monkeypatch, tmp_path):
    """The caller skipped the Solar download because the ensemble promised its
    own frame; if that frame cannot be had it must not just report nothing."""
    from affine import Affine

    from solarfit.providers.vision import CroppedImagery

    monkeypatch.setattr(get_settings(), "google_maps_api_key", "key")
    monkeypatch.setattr(satellite_frame, "_download_tile", lambda *a: None)  # e.g. Static Maps API not enabled
    fetched = {}
    solar = CroppedImagery(png_bytes=b"not a png", transform=Affine.identity(), crs=None, width=1, height=1)

    def _fetch(lat, lng):
        fetched["at"] = (lat, lng)
        return b"tiff"

    monkeypatch.setattr(yolo_module, "fetch_rgb_imagery", _fetch)
    monkeypatch.setattr(yolo_module, "crop_to_boundary", lambda imagery, boundary: solar)

    # The fallback imagery is undecodable here, which ends in [] - what matters
    # is that the Solar crop WAS fetched, at the roof's own centre.
    assert YoloEnsembleDetector([tmp_path / "a.pt"]).detect(None, _ROOF) == []
    assert fetched["at"] == pytest.approx((_LAT + _SPAN / 2, _LNG + _SPAN / 2))


def test_an_outline_mostly_off_the_roof_is_not_this_roofs_obstacle():
    roof = shape(_ROOF)
    inside = mapping(box(_LNG + 0.00005, _LAT + 0.00005, _LNG + 0.0001, _LAT + 0.0001))
    straddling = mapping(box(_LNG + 0.0002, _LAT + 0.0001, _LNG + 0.00026, _LAT + 0.00015))  # ~60 % on the roof
    next_door = mapping(box(_LNG + 0.00026, _LAT + 0.0001, _LNG + 0.0003, _LAT + 0.00015))

    assert _mostly_on_roof(inside, roof, 0.5)
    assert _mostly_on_roof(straddling, roof, 0.5)
    assert not _mostly_on_roof(next_door, roof, 0.5)
