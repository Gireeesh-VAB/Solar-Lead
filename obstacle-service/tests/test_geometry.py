import pytest
from affine import Affine
from shapely.geometry import box, mapping

from obstacle_service.geometry import clip_polygon_to_boundary, is_plausible_obstacle, mostly_on_roof, pixel_polygon_to_geojson
from obstacle_service.satellite_frame import Frame

# A ~25 m x 25 m roof in Hyderabad.
_LNG, _LAT, _SPAN = 78.4867, 17.385, 0.00023
_ROOF = box(_LNG, _LAT, _LNG + _SPAN, _LAT + _SPAN)


def test_pixel_polygon_is_georeferenced_through_the_frames_own_transform():
    # An EPSG:4326 frame with 0.00001-degree pixels starting at lng 78, lat 17.
    frame = Frame(png_bytes=b"", transform=Affine(0.00001, 0, 78.0, 0, -0.00001, 17.0), width=100, height=100, epsg=4326)
    geojson = pixel_polygon_to_geojson(box(10, 10, 20, 20), frame)

    ring = geojson["coordinates"][0]
    assert geojson["type"] == "Polygon" and ring[0] == ring[-1]
    lngs, lats = [p[0] for p in ring], [p[1] for p in ring]
    assert min(lngs) == pytest.approx(78.0001) and max(lngs) == pytest.approx(78.0002)
    assert max(lats) == pytest.approx(16.9999) and min(lats) == pytest.approx(16.9998)


def test_mostly_on_roof_uses_the_share_of_the_outlines_own_area():
    half_on = mapping(box(_LNG + _SPAN / 2, _LAT, _LNG + _SPAN * 1.5, _LAT + _SPAN))  # 50 % on the roof
    assert mostly_on_roof(half_on, _ROOF, 0.5) is True
    assert mostly_on_roof(half_on, _ROOF, 0.6) is False
    assert mostly_on_roof(mapping(box(0, 0, 1, 1)), _ROOF, 0.3) is False  # nowhere near


def test_a_straddling_outline_is_clipped_to_the_roof():
    straddler = mapping(box(_LNG + _SPAN * 0.5, _LAT, _LNG + _SPAN * 1.5, _LAT + _SPAN))
    clipped = clip_polygon_to_boundary(straddler, _ROOF)
    from shapely.geometry import shape

    assert _ROOF.covers(shape(clipped))


def test_an_outline_wholly_off_the_roof_clips_to_nothing_and_no_boundary_changes_nothing():
    off = mapping(box(0, 0, 1, 1))
    assert clip_polygon_to_boundary(off, _ROOF) is None
    assert clip_polygon_to_boundary(off, None) == off


def test_plausibility_rules():
    roof = mapping(_ROOF)
    ok = mapping(box(_LNG + _SPAN * 0.2, _LAT + _SPAN * 0.2, _LNG + _SPAN * 0.5, _LAT + _SPAN * 0.5))  # ~ 5 m x 5 m
    assert is_plausible_obstacle(ok, roof, min_area_m2=0.25, max_fraction=0.5) is True
    outside = mapping(box(_LNG + _SPAN * 0.8, _LAT, _LNG + _SPAN * 1.4, _LAT + _SPAN * 0.3))
    assert is_plausible_obstacle(outside, roof, min_area_m2=0.25, max_fraction=0.5) is False  # not inside the roof
    tiny = mapping(box(_LNG + _SPAN * 0.2, _LAT + _SPAN * 0.2, _LNG + _SPAN * 0.2 + 1e-7, _LAT + _SPAN * 0.2 + 1e-7))
    assert is_plausible_obstacle(tiny, roof, min_area_m2=0.25, max_fraction=0.5) is False  # noise-small
    huge = mapping(box(_LNG + _SPAN * 0.05, _LAT + _SPAN * 0.05, _LNG + _SPAN * 0.95, _LAT + _SPAN * 0.95))
    assert is_plausible_obstacle(huge, roof, min_area_m2=0.25, max_fraction=0.5) is False  # implausibly large for this roof
    assert is_plausible_obstacle({"type": "nope"}, roof, min_area_m2=0.25, max_fraction=0.5) is False
