"""§16 Testing — engine/panel_layout.py.

Turns Solar API solarPanels[] into map-drawable polygons. The tests that
matter most are the geometric ones: a panel drawn at the wrong size,
rotation or place would sit visibly off the customer's roof, and no unit
test of "did it return a list" would catch that. So the corners are
measured back in metres and checked against the dimensions Google gave.

The absence cases matter just as much — the one thing this module must
never do is invent a layout.
"""

import math

import pytest
from pyproj import Transformer
from shapely.geometry import Polygon

from solarfit.engine.panel_layout import (
    PanelLayout,
    fetch_panel_layout,
    panel_layout_from_insights,
)

LAT, LNG = 17.3850, 78.4867
PANEL_H, PANEL_W = 1.879, 1.045


def _insights(
    panels: list[dict] | None = None,
    segments: list[dict] | None = None,
    *,
    height: float | None = PANEL_H,
    width: float | None = PANEL_W,
    capacity: int | None = 400,
) -> dict:
    potential: dict = {
        "solarPanels": [] if panels is None else panels,
        "roofSegmentStats": segments if segments is not None else [_segment(0.0, 180.0)],
    }
    if height is not None:
        potential["panelHeightMeters"] = height
    if width is not None:
        potential["panelWidthMeters"] = width
    if capacity is not None:
        potential["panelCapacityWatts"] = capacity
    return {"solarPotential": potential}


def _segment(pitch: float, azimuth: float) -> dict:
    return {"pitchDegrees": pitch, "azimuthDegrees": azimuth}


def _panel(lat: float = LAT, lng: float = LNG, orientation: str = "PORTRAIT", segment: int = 0):
    return {
        "center": {"latitude": lat, "longitude": lng},
        "orientation": orientation,
        "segmentIndex": segment,
    }


def _xy_m(corners: list[tuple[float, float]]) -> list[tuple[float, float]]:
    to_m = Transformer.from_crs(
        "EPSG:4326",
        f"+proj=aeqd +lat_0={LAT} +lon_0={LNG} +datum=WGS84 +units=m +no_defs",
        always_xy=True,
    )
    return [to_m.transform(lng, lat) for lng, lat in corners]


def _sides_m(corners: list[tuple[float, float]]) -> tuple[float, float]:
    """The polygon's two side lengths, measured in metres."""
    xy = _xy_m(corners)
    lengths = [math.dist(xy[i], xy[(i + 1) % 4]) for i in range(4)]
    return min(lengths), max(lengths)


def _extent_along(corners: list[tuple[float, float]], bearing_deg: float) -> float:
    """Span of the polygon along a compass bearing, in metres.

    min/max of the side lengths cannot express this: past about 56 degrees
    of pitch the foreshortened long side becomes SHORTER than the panel's
    width, so "the longest edge" stops being the one running down the
    slope. Projecting onto the bearing measures the axis actually meant.
    """
    bearing = math.radians(bearing_deg)
    direction = (math.sin(bearing), math.cos(bearing))
    projected = [x * direction[0] + y * direction[1] for x, y in _xy_m(corners)]
    return max(projected) - min(projected)


# ---------------------------------------------------------------------------
# Geometry — real dimensions, real rotation, real position
# ---------------------------------------------------------------------------


def test_panel_polygon_has_four_corners_at_the_real_panel_size():
    layout = panel_layout_from_insights(_insights([_panel()]), LAT, LNG)

    assert layout.status == "ok"
    assert len(layout.panels) == 1
    corners = layout.panels[0].corners
    assert len(corners) == 4

    short, long = _sides_m(corners)
    assert short == pytest.approx(PANEL_W, abs=0.02)
    assert long == pytest.approx(PANEL_H, abs=0.02)


def test_panel_is_centred_on_googles_own_coordinates():
    layout = panel_layout_from_insights(_insights([_panel()]), LAT, LNG)
    poly = Polygon(layout.panels[0].corners)

    assert poly.centroid.x == pytest.approx(LNG, abs=1e-6)
    assert poly.centroid.y == pytest.approx(LAT, abs=1e-6)


def test_landscape_and_portrait_swap_the_long_axis():
    """Google reports orientation per panel; drawing them all one way
    would misrepresent the array."""
    segments = [_segment(0.0, 180.0)]  # flat, so no foreshortening either way
    portrait = panel_layout_from_insights(
        _insights([_panel(orientation="PORTRAIT")], segments), LAT, LNG
    )
    landscape = panel_layout_from_insights(
        _insights([_panel(orientation="LANDSCAPE")], segments), LAT, LNG
    )

    p_corners = portrait.panels[0].corners
    l_corners = landscape.panels[0].corners
    # Same module, turned 90 degrees: the two footprints are not the same.
    assert p_corners != l_corners
    # Both still measure one panel.
    for corners in (p_corners, l_corners):
        short, long = _sides_m(corners)
        assert short == pytest.approx(PANEL_W, abs=0.02)
        assert long == pytest.approx(PANEL_H, abs=0.02)


def test_panel_is_rotated_to_its_roof_segment_azimuth():
    """A panel on a south-facing roof and one on an east-facing roof must
    not be drawn identically."""
    south = panel_layout_from_insights(
        _insights([_panel()], [_segment(0.0, 180.0)]), LAT, LNG
    ).panels[0]
    east = panel_layout_from_insights(
        _insights([_panel()], [_segment(0.0, 90.0)]), LAT, LNG
    ).panels[0]

    assert south.azimuth_degrees == 180.0
    assert east.azimuth_degrees == 90.0
    assert south.corners != east.corners

    # A 90-degree turn swaps which axis runs north-south.
    s_poly, e_poly = Polygon(south.corners), Polygon(east.corners)
    s_w, s_h = (s_poly.bounds[2] - s_poly.bounds[0]), (s_poly.bounds[3] - s_poly.bounds[1])
    e_w, e_h = (e_poly.bounds[2] - e_poly.bounds[0]), (e_poly.bounds[3] - e_poly.bounds[1])
    assert (s_h > s_w) != (e_h > e_w)


def test_pitched_panels_are_foreshortened_in_plan_view():
    """The map looks straight down, so a panel on a steep roof covers less
    ground than a flat one. Drawing it full length would overstate the
    array's footprint."""
    flat = panel_layout_from_insights(
        _insights([_panel()], [_segment(0.0, 180.0)]), LAT, LNG
    ).panels[0]
    steep = panel_layout_from_insights(
        _insights([_panel()], [_segment(60.0, 180.0)]), LAT, LNG
    ).panels[0]

    # Measured down the slope (the segment's own azimuth), which is the
    # axis foreshortening acts on.
    flat_along = _extent_along(flat.corners, 180.0)
    steep_along = _extent_along(steep.corners, 180.0)

    assert flat_along == pytest.approx(PANEL_H, abs=0.02)
    assert steep_along == pytest.approx(PANEL_H * math.cos(math.radians(60.0)), abs=0.02)
    # Across the slope the panel keeps its full width — foreshortening is
    # one-directional, not an overall shrink.
    assert _extent_along(steep.corners, 90.0) == pytest.approx(PANEL_W, abs=0.02)


def test_panels_do_not_overlap_each_other():
    """Neighbouring panels an exact panel-width apart must tile, not stack."""
    metres_per_deg_lng = 111_320 * math.cos(math.radians(LAT))
    layout = panel_layout_from_insights(
        _insights(
            [_panel(lng=LNG + i * (PANEL_W / metres_per_deg_lng)) for i in range(3)],
            [_segment(0.0, 0.0)],
        ),
        LAT,
        LNG,
    )

    polys = [Polygon(p.corners) for p in layout.panels]
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            assert polys[i].intersection(polys[j]).area < 0.05 * polys[i].area


def test_panel_carries_its_real_metadata():
    layout = panel_layout_from_insights(
        _insights([_panel(orientation="LANDSCAPE", segment=0)], [_segment(12.5, 210.0)]), LAT, LNG
    )
    panel = layout.panels[0]

    assert panel.capacity_watts == 400
    assert panel.orientation == "LANDSCAPE"
    assert panel.segment_index == 0
    assert panel.azimuth_degrees == 210.0
    assert panel.pitch_degrees == 12.5


def test_total_kwp_is_the_layouts_own_figure():
    layout = panel_layout_from_insights(_insights([_panel(), _panel(), _panel()]), LAT, LNG)
    assert layout.total_kwp == pytest.approx(1.2)  # 3 x 400 W — Google's, not P2's


# ---------------------------------------------------------------------------
# Absence — the one thing this module must never do is invent a layout
# ---------------------------------------------------------------------------


def test_no_coverage_when_the_solar_api_has_no_building():
    layout = panel_layout_from_insights({}, LAT, LNG)

    assert layout.status == "no_coverage"
    assert layout.panels == []
    assert layout.reason


def test_zero_panels_is_reported_not_fabricated():
    layout = panel_layout_from_insights(_insights([]), LAT, LNG)

    assert layout.status == "no_layout"
    assert layout.panels == []


@pytest.mark.parametrize("missing", ["height", "width"])
def test_missing_panel_dimensions_produce_no_panels(missing):
    """Guessing a module size would put fabricated dimensions on a
    customer's roof."""
    kwargs = {missing: None}
    layout = panel_layout_from_insights(_insights([_panel()], **kwargs), LAT, LNG)

    assert layout.status == "no_layout"
    assert layout.panels == []


def test_panels_without_coordinates_are_skipped():
    layout = panel_layout_from_insights(
        _insights([{"orientation": "PORTRAIT", "segmentIndex": 0}, _panel()]), LAT, LNG
    )

    assert layout.status == "ok"
    assert len(layout.panels) == 1  # the coordinate-less entry is dropped, not placed


def test_panel_with_unknown_segment_still_draws_without_rotation_data():
    """A segmentIndex pointing nowhere must not lose the panel — it is
    still a real panel at a real location."""
    layout = panel_layout_from_insights(_insights([_panel(segment=99)]), LAT, LNG)

    assert layout.status == "ok"
    assert len(layout.panels) == 1
    assert layout.panels[0].azimuth_degrees == 0.0


def test_api_failure_is_reported_and_never_raises(monkeypatch):
    """VIS-04 discipline: the overlay goes missing, the page does not."""
    from solarfit.providers import vision

    def boom(lat, lng):
        raise RuntimeError("network down")

    monkeypatch.setattr(vision, "fetch_building_insights", boom)
    layout = fetch_panel_layout(LAT, LNG)

    assert isinstance(layout, PanelLayout)
    assert layout.status == "error"
    assert layout.panels == []
    assert layout.reason


def test_no_coverage_flows_through_the_real_fetch(monkeypatch):
    from solarfit.providers import vision

    monkeypatch.setattr(vision, "fetch_building_insights", lambda lat, lng: {})
    assert fetch_panel_layout(LAT, LNG).status == "no_coverage"
