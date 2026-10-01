"""§16 Testing — packing real panels into the usable roof polygon.

Capacity has been an area times a density constant, which can never say
WHERE panels go. This lays actual modules in the actual shape, so the two
things that matter are: every panel is genuinely on the roof, and the
spacing rules are applied exactly once.

The double-derate guard has its own section. Applying AREA-05's
utilisation factor to a packed count charges twice for the same walkways
and would quietly hand a customer a system a third smaller than their
roof supports — and a quietly undersized system looks entirely plausible
on a result page, which is what makes it worth raising over.
"""

import math

import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from solarfit.engine.panel_packing import (
    PackedLayout,
    PackedPanel,
    assert_not_double_derated,
    pack_panels,
    pack_panels_best_orientation,
    row_gap_m,
    select_for_target_capacity,
    solar_noon_altitude_deg,
    to_wgs84_rings,
)
from solarfit.engine.panel_validation import validate_layout

HYDERABAD_LAT = 17.385
PANEL_L, PANEL_W = 1.879, 1.045


def _square(side: float) -> Polygon:
    return box(0.0, 0.0, side, side)


def _l_shape() -> Polygon:
    """A 20 x 20 m roof with a 10 x 10 m bite out of one corner."""
    return Polygon([(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)])


def _multi_square() -> MultiPolygon:
    """Two disjoint 10x10 squares — the MultiPolygon shape a real setback/
    exclusion difference can produce for an irregular roof."""
    return MultiPolygon([_square(10.0), box(20.0, 0.0, 30.0, 10.0)])


# ---------------------------------------------------------------------------
# Row spacing — derived, not guessed
# ---------------------------------------------------------------------------


def test_winter_noon_altitude_falls_with_latitude():
    """The worst case a spacing rule must survive."""
    assert solar_noon_altitude_deg(0.0) == pytest.approx(66.55)
    assert solar_noon_altitude_deg(17.385) == pytest.approx(49.165)
    assert solar_noon_altitude_deg(51.5) == pytest.approx(15.05)


def test_the_hemisphere_does_not_matter():
    assert solar_noon_altitude_deg(-17.385) == solar_noon_altitude_deg(17.385)


def test_a_polar_latitude_cannot_produce_an_infinite_gap():
    """Unfloored, the formula goes negative and tan() flips sign — a row
    gap of minus infinity would pack panels on top of each other."""
    assert solar_noon_altitude_deg(89.0) > 0
    assert row_gap_m(PANEL_L, 20.0, 89.0, 0.3) > 0


def test_a_steeper_tilt_needs_a_bigger_gap():
    flat = row_gap_m(PANEL_L, 5.0, HYDERABAD_LAT, 0.0)
    steep = row_gap_m(PANEL_L, 30.0, HYDERABAD_LAT, 0.0)
    assert steep > flat


def test_a_higher_latitude_needs_a_bigger_gap():
    """Same array, lower winter sun, longer shadow."""
    hyderabad = row_gap_m(PANEL_L, 15.0, 17.385, 0.0)
    london = row_gap_m(PANEL_L, 15.0, 51.5, 0.0)
    assert london > hyderabad


def test_the_gap_matches_the_shadow_it_is_derived_from():
    rise = PANEL_L * math.sin(math.radians(15.0))
    expected = rise / math.tan(math.radians(solar_noon_altitude_deg(HYDERABAD_LAT)))
    assert row_gap_m(PANEL_L, 15.0, HYDERABAD_LAT, 0.0) == pytest.approx(expected)


def test_the_floor_wins_for_a_flat_array():
    """A flat panel casts no shadow, but rows still need airflow and a
    way to reach them."""
    assert row_gap_m(PANEL_L, 0.0, HYDERABAD_LAT, 0.3) == 0.3


# ---------------------------------------------------------------------------
# Packing — every panel genuinely on the roof
# ---------------------------------------------------------------------------


def test_every_packed_panel_lies_inside_the_usable_polygon():
    """The whole point. A panel overhanging the roof edge cannot be
    installed there, so `contains` is the test, not `intersects`."""
    roof = _square(20.0)
    layout = pack_panels(roof, latitude_deg=HYDERABAD_LAT, tilt_deg=15.0, azimuth_deg=180.0)

    assert layout.count > 0
    for panel in layout.panels:
        assert roof.contains(panel.footprint)


def test_panels_do_not_overlap_each_other():
    layout = pack_panels(_square(20.0), latitude_deg=HYDERABAD_LAT, tilt_deg=15.0)
    shapes = [p.footprint for p in layout.panels]

    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            assert shapes[i].intersection(shapes[j]).area < 1e-6


def test_each_panel_has_the_real_module_footprint():
    """Tilted, so the ground footprint is shorter than the panel."""
    layout = pack_panels(_square(20.0), latitude_deg=HYDERABAD_LAT, tilt_deg=15.0, azimuth_deg=0.0)
    footprint = layout.panels[0].footprint
    min_x, min_y, max_x, max_y = footprint.bounds

    assert (max_x - min_x) == pytest.approx(PANEL_W, abs=0.02)
    assert (max_y - min_y) == pytest.approx(PANEL_L * math.cos(math.radians(15.0)), abs=0.02)


def test_an_l_shaped_roof_is_followed_not_bounded():
    """The shape this whole feature exists for. Panels must fill the L and
    none may stray into the bite — a bounding-box packer would put them
    exactly there."""
    roof = _l_shape()
    bite = box(10, 10, 20, 20)
    layout = pack_panels(roof, latitude_deg=HYDERABAD_LAT, tilt_deg=10.0, azimuth_deg=180.0)

    assert layout.count > 0
    for panel in layout.panels:
        assert roof.contains(panel.footprint)
        assert panel.footprint.intersection(bite).area < 1e-6


def test_an_exclusion_hole_is_respected():
    """Exclusions arrive already cut out of the polygon by AREA-02/04, so
    a hole must simply come out empty."""
    roof = Polygon(
        [(0, 0), (20, 0), (20, 20), (0, 20)],
        holes=[[(8, 8), (12, 8), (12, 12), (8, 12)]],
    )
    layout = pack_panels(roof, latitude_deg=HYDERABAD_LAT, tilt_deg=10.0)

    tank = box(8, 8, 12, 12)
    for panel in layout.panels:
        assert panel.footprint.intersection(tank).area < 1e-6


def test_a_roof_too_small_for_one_panel_packs_nothing():
    layout = pack_panels(_square(0.8), latitude_deg=HYDERABAD_LAT)

    assert layout.count == 0
    assert layout.kwp == 0.0


def test_an_empty_polygon_is_handled_not_crashed():
    """AREA-06's consumed roof arrives as None — a real answer."""
    assert pack_panels(None, latitude_deg=HYDERABAD_LAT).count == 0
    assert pack_panels(Polygon(), latitude_deg=HYDERABAD_LAT).count == 0


def test_azimuth_rotates_the_whole_grid():
    """Rows follow the roof. Packing north-aligned and rotating each panel
    in place would leave unusable slivers along every angled edge."""
    roof = _square(20.0)
    south = pack_panels(roof, latitude_deg=HYDERABAD_LAT, tilt_deg=15.0, azimuth_deg=180.0)
    diagonal = pack_panels(roof, latitude_deg=HYDERABAD_LAT, tilt_deg=15.0, azimuth_deg=135.0)

    assert south.count > 0 and diagonal.count > 0
    south_bounds = south.panels[0].footprint.bounds
    diag_bounds = diagonal.panels[0].footprint.bounds
    # A 45-degree turn cannot leave an axis-aligned rectangle unchanged.
    assert (diag_bounds[2] - diag_bounds[0]) != pytest.approx(
        south_bounds[2] - south_bounds[0], abs=0.01
    )


def test_capacity_is_the_panel_count_times_real_wattage():
    layout = pack_panels(_square(20.0), latitude_deg=HYDERABAD_LAT, panel_watts=550)

    assert layout.panel_watts == 550
    assert layout.kwp == pytest.approx(layout.count * 550 / 1000.0)


def test_the_solar_apis_own_panel_size_is_preferred_when_given():
    big = pack_panels(
        _square(20.0), latitude_deg=HYDERABAD_LAT, panel_length_m=3.0, panel_width_m=2.0
    )
    default = pack_panels(_square(20.0), latitude_deg=HYDERABAD_LAT)

    assert big.count < default.count  # larger modules, fewer of them


def test_rings_come_back_as_drawable_coordinates():
    layout = pack_panels(_square(20.0), latitude_deg=HYDERABAD_LAT)
    # A metric square at the origin is not a real place; 32644 just has to
    # round-trip.
    rings = to_wgs84_rings(layout, epsg=32644)

    assert len(rings) == layout.count
    assert all(len(ring) == 4 for ring in rings)
    assert all(len(point) == 2 for ring in rings for point in ring)


# ---------------------------------------------------------------------------
# Capping a full layout at the customer's recommended capacity — not the
# roof's technical maximum (CON-07: don't fill a roof nobody asked to fill)
# ---------------------------------------------------------------------------


def test_selection_stops_at_the_target_not_the_full_roof():
    full = pack_panels(_square(20.0), latitude_deg=HYDERABAD_LAT, tilt_deg=15.0)
    assert full.count > 3  # the square roof comfortably fits more than this

    target_kwp = 3 * full.panel_watts / 1000.0  # room for exactly 3 panels
    selected = select_for_target_capacity(full, target_kwp)

    assert selected.count == 3
    assert selected.count < full.count


def test_selection_keeps_every_panel_when_the_target_exceeds_the_roof():
    full = pack_panels(_square(20.0), latitude_deg=HYDERABAD_LAT, tilt_deg=15.0)
    selected = select_for_target_capacity(full, target_kwp=full.kwp * 10)

    assert selected.count == full.count


def test_selection_is_empty_without_a_target():
    full = pack_panels(_square(20.0), latitude_deg=HYDERABAD_LAT, tilt_deg=15.0)

    assert select_for_target_capacity(full, None).count == 0
    assert select_for_target_capacity(full, 0).count == 0
    assert select_for_target_capacity(full, -5).count == 0


def test_selected_panels_are_still_the_real_footprints():
    """A selection is a subset, not a re-pack — every kept panel must still
    be one of the originally packed, roof-contained footprints."""
    roof = _square(20.0)
    full = pack_panels(roof, latitude_deg=HYDERABAD_LAT, tilt_deg=15.0)
    selected = select_for_target_capacity(full, target_kwp=full.kwp / 2)

    kept_footprints = {id(p) for p in selected.panels}
    assert kept_footprints.issubset({id(p) for p in full.panels})
    for panel in selected.panels:
        assert roof.contains(panel.footprint)


# ---------------------------------------------------------------------------
# The double-derate guard
# ---------------------------------------------------------------------------


def test_applying_the_utilisation_factor_to_a_packed_count_raises():
    """The mistake this exists to prevent: the packer already placed the
    walkways and row gaps that utilisation stands in for."""
    with pytest.raises(ValueError, match="already placed the walkways"):
        assert_not_double_derated(16.0, 0.7)


def test_the_error_shows_what_it_would_have_cost():
    """A number in the message is what makes the mistake obvious."""
    with pytest.raises(ValueError) as exc:
        assert_not_double_derated(16.0, 0.7)

    assert "16.00" in str(exc.value)
    assert "11.20" in str(exc.value)


def test_a_factor_of_one_is_not_a_derate_and_passes():
    assert_not_double_derated(16.0, 1.0)


@pytest.mark.parametrize("bad", [0.0, -0.5, 1.5])
def test_a_nonsensical_factor_is_rejected(bad):
    with pytest.raises(ValueError, match="out of range"):
        assert_not_double_derated(16.0, bad)


def test_a_packed_layout_is_smaller_than_the_density_estimate():
    """Expected, and not a bug: 0.2 kWp/m2 assumes wall-to-wall coverage,
    while a real layout loses area to walkways, row gaps and edges that do
    not divide evenly. Pinned so the difference is never mistaken for one."""
    roof = _square(20.0)
    layout = pack_panels(roof, latitude_deg=HYDERABAD_LAT, tilt_deg=15.0)

    density_estimate = roof.area * 0.2
    assert layout.kwp < density_estimate


# ---------------------------------------------------------------------------
# Regression: the new fields are additive, not a behaviour change
# ---------------------------------------------------------------------------


def test_a_plain_rectangle_is_unaffected_by_the_new_fields():
    layout = pack_panels(_square(20.0), latitude_deg=HYDERABAD_LAT, tilt_deg=15.0, azimuth_deg=180.0)

    assert layout.count > 0
    assert layout.rejected_count == 0
    assert layout.orientation == "portrait"


# ---------------------------------------------------------------------------
# rejected_count — geometry rejections tracked, not just accepted panels
# ---------------------------------------------------------------------------


def test_rejected_count_tracks_candidates_that_failed_containment():
    """The L-shape's notch necessarily produces candidate rectangles that
    straddle the missing corner and get rejected by working.contains()."""
    layout = pack_panels(_l_shape(), latitude_deg=HYDERABAD_LAT, tilt_deg=10.0, azimuth_deg=180.0)

    assert layout.rejected_count > 0


def test_rejected_count_is_zero_for_a_plain_rectangle():
    """A plain axis-aligned rectangle's bounding box IS the shape itself,
    so every candidate the x/y loop's own bounds admit is automatically
    contained — rejections only happen for a concave shape like the L."""
    layout = pack_panels(_square(20.0), latitude_deg=HYDERABAD_LAT, tilt_deg=15.0, azimuth_deg=180.0)

    assert layout.count > 0
    assert layout.rejected_count == 0


# ---------------------------------------------------------------------------
# pack_panels_best_orientation — tries both, keeps the better one
# ---------------------------------------------------------------------------


def test_pack_panels_reports_its_own_orientation_on_the_layout():
    landscape = pack_panels(
        _square(20.0), latitude_deg=HYDERABAD_LAT, params={"orientation": "landscape"}
    )
    portrait = pack_panels(
        _square(20.0), latitude_deg=HYDERABAD_LAT, params={"orientation": "portrait"}
    )

    assert landscape.orientation == "landscape"
    assert portrait.orientation == "portrait"


def test_pack_panels_best_orientation_picks_the_orientation_with_more_panels():
    roof = _square(20.0)
    best = pack_panels_best_orientation(roof, latitude_deg=HYDERABAD_LAT, tilt_deg=15.0)
    portrait = pack_panels(roof, latitude_deg=HYDERABAD_LAT, tilt_deg=15.0, params={"orientation": "portrait"})
    landscape = pack_panels(
        roof, latitude_deg=HYDERABAD_LAT, tilt_deg=15.0, params={"orientation": "landscape"}
    )

    assert best.count == max(portrait.count, landscape.count)
    assert best.orientation == ("portrait" if portrait.count >= landscape.count else "landscape")


def test_pack_panels_best_orientation_ties_prefer_portrait():
    # An empty/impossible-to-pack roof ties at zero for both orientations.
    best = pack_panels_best_orientation(_square(0.1), latitude_deg=HYDERABAD_LAT)
    assert best.orientation == "portrait"


# ---------------------------------------------------------------------------
# engine/panel_validation.py — an independent re-check, not a rubber stamp
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "roof",
    [_square(20.0), _l_shape(), _multi_square(), box(0.0, 0.0, 15.0, 25.0)],
)
def test_no_panel_ever_falls_outside_the_usable_polygon(roof):
    layout = pack_panels_best_orientation(roof, latitude_deg=HYDERABAD_LAT, tilt_deg=12.0, azimuth_deg=170.0)
    validation = validate_layout(layout, roof)

    assert validation.panels_outside_roof == 0
    assert validation.ok


def test_validate_layout_flags_a_panel_deliberately_placed_outside_the_roof():
    """Proves the validator actually catches something — not always zero
    by construction."""
    roof = _square(20.0)
    bad_panel = PackedPanel(footprint=box(25.0, 25.0, 27.0, 27.0), watts=400.0, row=0)
    layout = PackedLayout([bad_panel], panel_watts=400.0, tilt_deg=15.0, azimuth_deg=180.0, row_gap_m=0.3)

    validation = validate_layout(layout, roof)

    assert validation.panels_outside_roof == 1
    assert not validation.ok


def test_validate_layout_flags_intersection_with_exclusions():
    roof = _square(20.0)
    layout = pack_panels(roof, latitude_deg=HYDERABAD_LAT, tilt_deg=10.0, azimuth_deg=180.0)
    assert layout.count > 0

    # A synthetic exclusion overlapping exactly one packed panel's footprint.
    exclusion = layout.panels[0].footprint

    validation = validate_layout(layout, roof, exclusions_metric=exclusion)

    assert validation.panels_intersecting_obstacles >= 1
    assert not validation.ok
