"""Tests for routers/assessments.py's panel-packing wiring
(_pack_panel_layout, _segment_polygon_metric, _segment_quality_score,
_building_match_warning) — the fix for panels drawn outside the roof, in
the wrong orientation, across unsuitable sections, or ignoring obstacles.

Previously the frontend drew Google's raw solarPanels[] array, computed
against Google's own building footprint, with no relationship to this
app's resolved boundary/exclusions/capacity (Phase 1). Phase 1 then
packed the whole roof as a single dominant plane. This phase packs EVERY
Building Insights roof segment independently against its own tilt/
azimuth and its own share of the usable polygon, best-performing plane
first — never one shared orientation forced across the whole roof.
"""

import pytest
from pyproj import Transformer
from shapely.geometry import box as shapely_box
from shapely.geometry import mapping
from shapely.ops import transform

import solarfit.routers.assessments as router_module
from solarfit.engine.area import UsableRoof, compute_usable_roof

_ORIGIN_LON, _ORIGIN_LAT = 78.4867, 17.3850

_to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True).transform
_to_wgs84_t = Transformer.from_crs("EPSG:32644", "EPSG:4326", always_xy=True).transform


def _square_4326(side_m: float, *, offset_x: float = 0.0, offset_y: float = 0.0) -> dict:
    x0, y0 = _to_utm(_ORIGIN_LON, _ORIGIN_LAT)
    x0, y0 = x0 + offset_x, y0 + offset_y
    square = shapely_box(x0, y0, x0 + side_m, y0 + side_m)
    return mapping(transform(_to_wgs84_t, square))


def _bbox_around(side_m: float, *, offset_x: float = 0.0, offset_y: float = 0.0) -> dict:
    """A Building Insights-shaped {sw, ne} boundingBox covering the same
    square area a segment's real bbox would (real segments carry their
    own boundingBox — see providers/solar_api.py::bounding_box_to_polygon)."""
    poly = _square_4326(side_m, offset_x=offset_x, offset_y=offset_y)
    lngs = [pt[0] for pt in poly["coordinates"][0]]
    lats = [pt[1] for pt in poly["coordinates"][0]]
    return {
        "sw": {"latitude": min(lats), "longitude": min(lngs)},
        "ne": {"latitude": max(lats), "longitude": max(lngs)},
    }


def _segment(*, azimuth=180.0, pitch=15.0, area=100.0, bbox_side_m=30.0, offset_x=0.0, offset_y=0.0):
    return {
        "azimuthDegrees": azimuth,
        "pitchDegrees": pitch,
        "stats": {"areaMeters2": area, "groundAreaMeters2": area * 0.9, "sunshineQuantiles": []},
        "boundingBox": _bbox_around(bbox_side_m, offset_x=offset_x, offset_y=offset_y),
    }


def _insights(*, with_bbox=True, segments=None):
    payload = {"solarPotential": {"roofSegmentStats": segments if segments is not None else [_segment()]}}
    if with_bbox:
        payload["boundingBox"] = {
            "sw": {"latitude": _ORIGIN_LAT - 0.0002, "longitude": _ORIGIN_LON - 0.0002},
            "ne": {"latitude": _ORIGIN_LAT + 0.0002, "longitude": _ORIGIN_LON + 0.0002},
        }
    return payload


# ---------------------------------------------------------------------------
# _building_match_warning — coarse "did the Solar API resolve to the right
# building" sanity check
# ---------------------------------------------------------------------------


def test_pin_inside_the_returned_bounding_box_gets_no_warning():
    insights = _insights()
    assert router_module._building_match_warning(_ORIGIN_LAT, _ORIGIN_LON, insights) is None


def test_pin_nowhere_near_the_returned_building_gets_a_warning():
    insights = _insights()
    far_lat, far_lng = _ORIGIN_LAT + 1.0, _ORIGIN_LON + 1.0  # ~150km away

    warning = router_module._building_match_warning(far_lat, far_lng, insights)

    assert warning is not None
    assert "neighbouring building" in warning


def test_a_missing_bounding_box_is_not_treated_as_a_mismatch():
    """Absence of data is not evidence of a wrong building — never invent
    a warning from information that simply isn't there."""
    assert router_module._building_match_warning(_ORIGIN_LAT, _ORIGIN_LON, {}) is None


def test_a_pin_just_outside_the_box_within_the_margin_is_still_fine():
    """Buildings vary in size — a pin a few tens of metres from a tight
    bounding box is ordinary, not a mismatch."""
    insights = _insights()
    nudged_lat = _ORIGIN_LAT + 0.0003  # inside the configured margin
    assert router_module._building_match_warning(nudged_lat, _ORIGIN_LON, insights) is None


# ---------------------------------------------------------------------------
# _segment_quality_score — ranking roof planes best-first
# ---------------------------------------------------------------------------


def test_a_segment_with_higher_median_sunshine_scores_higher():
    sunnier = {"stats": {"sunshineQuantiles": [900, 1000, 1100]}}
    shadier = {"stats": {"sunshineQuantiles": [400, 500, 600]}}
    assert router_module._segment_quality_score(sunnier) > router_module._segment_quality_score(shadier)


def test_without_sunshine_data_a_south_facing_moderate_pitch_segment_scores_higher():
    south = {"azimuthDegrees": 180.0, "pitchDegrees": 20.0}
    north = {"azimuthDegrees": 0.0, "pitchDegrees": 20.0}
    assert router_module._segment_quality_score(south) > router_module._segment_quality_score(north)


def test_a_segment_missing_orientation_and_sunshine_scores_lowest_not_crashes():
    assert router_module._segment_quality_score({}) == 0.0


# ---------------------------------------------------------------------------
# _pack_panel_layout — the real packing, per segment, wired to real inputs
# ---------------------------------------------------------------------------


def test_no_layout_without_a_resolved_boundary(make_capacity):
    """AREA-06: a setback/exclusion that consumed the whole roof leaves
    polygon_metric None — nothing to pack, and that must not crash."""
    usable_roof = UsableRoof(area_m2=0.0, polygon=None, polygon_metric=None, epsg=None)
    capacity = make_capacity(recommended_kwp=4.0)

    layout, segments, warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    assert layout is None
    assert segments is None
    assert warning is None


def test_no_layout_without_a_resolved_capacity(make_site, make_capacity):
    """A site with real usable roof but zero recommended capacity (e.g.
    every ceiling was insufficient_data) must not draw a layout for a
    system size that was never actually resolved."""
    site = make_site(boundary=_square_4326(20.0))
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=0.0)

    layout, segments, warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    assert layout is None
    assert segments is None
    assert warning is None


def test_packing_is_capped_at_the_recommended_capacity(make_site, make_capacity, monkeypatch):
    site = make_site(boundary=_square_4326(20.0))
    usable_roof = compute_usable_roof(site)
    assert usable_roof.polygon_metric is not None  # sanity: a real polygon to pack into

    # A tiny target — a fraction of a single panel's worth (400W default
    # config) — so the packer should stop at exactly one panel.
    capacity = make_capacity(recommended_kwp=0.1)
    monkeypatch.setattr(
        router_module,
        "fetch_building_insights",
        lambda lat, lng: _insights(segments=[_segment(bbox_side_m=20.0)]),
    )

    layout, segments, warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    assert layout is not None
    assert layout["status"] == "ok"
    assert layout["panelCount"] == 1
    assert segments is not None
    assert len(segments["segments"]) == 1
    assert warning is None  # pin sits inside the mocked building's bbox


def test_packed_panel_count_never_exceeds_what_the_roof_can_hold(make_site, make_capacity, monkeypatch):
    site = make_site(boundary=_square_4326(20.0))
    usable_roof = compute_usable_roof(site)

    # An enormous target — the roof's own technical ceiling wins.
    capacity = make_capacity(recommended_kwp=10_000.0)
    monkeypatch.setattr(
        router_module,
        "fetch_building_insights",
        lambda lat, lng: _insights(segments=[_segment(bbox_side_m=20.0)]),
    )

    layout, _segments, _warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    assert layout is not None
    assert layout["panelCount"] < 200  # a 20x20m roof cannot hold thousands of panels


def test_a_building_insights_failure_degrades_to_no_layout(make_site, make_capacity, monkeypatch):
    """Never blocks the assessment — same discipline as every other Solar
    API consumer in this codebase."""
    site = make_site(boundary=_square_4326(20.0))
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=4.0)

    def _boom(lat, lng):
        raise RuntimeError("Solar API unavailable")

    monkeypatch.setattr(router_module, "fetch_building_insights", _boom)

    layout, segments, warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    assert layout is None
    assert segments is None
    assert warning is None


def test_no_solar_api_coverage_degrades_to_no_layout(make_site, make_capacity, monkeypatch):
    site = make_site(boundary=_square_4326(20.0))
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=4.0)

    monkeypatch.setattr(router_module, "fetch_building_insights", lambda lat, lng: {})

    layout, segments, warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    assert layout is None
    assert segments is None
    assert warning is None


def test_no_roof_segments_falls_back_to_a_single_plane_packed_into_the_whole_usable_roof(
    make_site, make_capacity, monkeypatch
):
    """A response that resolved but carries no roofSegmentStats used to
    give up entirely — a manually-drawn or imported boundary (or any site
    Google's segments don't cover) still has a perfectly packable usable
    polygon, so it now gets a real single-plane layout instead of nothing."""
    site = make_site(boundary=_square_4326(20.0))
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=4.0)

    monkeypatch.setattr(
        router_module, "fetch_building_insights", lambda lat, lng: _insights(segments=[])
    )

    layout, segments, _warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    assert layout is not None
    assert layout["status"] == "ok"
    assert layout["panelCount"] > 0
    assert all(panel["segmentIndex"] is None for panel in layout["panels"])
    assert layout["validation"]["panelsOutsideRoof"] == 0
    # No per-plane Building Insights data exists for this path.
    assert segments is None


def test_fallback_single_plane_uses_config_pack_default_tilt_and_azimuth(
    make_site, make_capacity, monkeypatch
):
    site = make_site(boundary=_square_4326(20.0))
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=4.0)

    monkeypatch.setattr(
        router_module, "fetch_building_insights", lambda lat, lng: _insights(segments=[])
    )

    layout, _segments, _warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    params = router_module.config_pack.get_panel_packing_params()
    assert layout["panels"][0]["tiltDeg"] == params["default_tilt_deg"]
    assert layout["panels"][0]["azimuthDeg"] == params["default_azimuth_deg"]


def test_fallback_single_plane_respects_recommended_capacity_cap(make_site, make_capacity, monkeypatch):
    site = make_site(boundary=_square_4326(20.0))
    usable_roof = compute_usable_roof(site)
    small_capacity = make_capacity(recommended_kwp=0.4)  # a single panel's worth

    monkeypatch.setattr(
        router_module, "fetch_building_insights", lambda lat, lng: _insights(segments=[])
    )

    layout, _segments, _warning = router_module._pack_panel_layout(
        usable_roof, small_capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    assert layout["panelCount"] >= 1
    assert layout["totalKwp"] <= 0.5


def test_fallback_single_plane_returns_no_layout_when_usable_roof_too_small_to_fit_a_panel(
    make_site, make_capacity, monkeypatch
):
    # After the default 0.5m edge setback this leaves roughly a 1m x 1m
    # usable polygon — non-empty, but smaller than any real panel footprint.
    site = make_site(boundary=_square_4326(2.0))
    usable_roof = compute_usable_roof(site)
    assert usable_roof.polygon_metric is not None
    capacity = make_capacity(recommended_kwp=4.0)

    monkeypatch.setattr(
        router_module, "fetch_building_insights", lambda lat, lng: _insights(segments=[])
    )

    layout, _segments, _warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    assert layout["status"] == "no_layout"


def test_pack_panel_layout_includes_a_validation_block_with_zero_violations(
    make_site, make_capacity, monkeypatch
):
    site = make_site(boundary=_square_4326(20.0))
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=4.0)

    monkeypatch.setattr(router_module, "fetch_building_insights", lambda lat, lng: _insights())

    layout, _segments, _warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    assert layout["validation"]["panelsOutsideRoof"] == 0
    assert layout["validation"]["panelsIntersectingObstacles"] == 0
    assert layout["validation"]["panelCount"] == layout["panelCount"]


def test_a_mismatched_building_still_reports_the_warning_even_if_packing_fails(
    make_site, make_capacity, monkeypatch
):
    """The building-match warning is independent of whether packing itself
    succeeds — a customer should hear about a likely wrong building even
    when there's otherwise nothing to draw."""
    site = make_site(boundary=_square_4326(20.0))
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=4.0)

    far_insights = _insights(segments=[_segment(bbox_side_m=20.0)])
    far_insights["boundingBox"] = {
        "sw": {"latitude": _ORIGIN_LAT + 1.0, "longitude": _ORIGIN_LON + 1.0},
        "ne": {"latitude": _ORIGIN_LAT + 1.001, "longitude": _ORIGIN_LON + 1.001},
    }
    monkeypatch.setattr(router_module, "fetch_building_insights", lambda lat, lng: far_insights)

    layout, segments, warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    assert warning is not None
    assert "neighbouring building" in warning
    # Packing itself still runs against the pin's own resolved boundary —
    # the mismatch is a warning, not a hard stop.
    assert layout is not None
    assert segments is not None


def test_a_segment_with_no_boundingbox_is_skipped_not_crashed_on(make_site, make_capacity, monkeypatch):
    """A malformed/missing segment boundingBox must degrade that ONE
    segment, not the whole packing pass."""
    site = make_site(boundary=_square_4326(20.0))
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=4.0)

    broken = {"azimuthDegrees": 180.0, "pitchDegrees": 15.0, "stats": {"areaMeters2": 50.0}}
    monkeypatch.setattr(
        router_module, "fetch_building_insights", lambda lat, lng: _insights(segments=[broken])
    )

    layout, segments, _warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    assert layout is not None
    assert layout["status"] == "no_layout"
    assert segments is not None
    assert segments["segments"][0]["segmentIndex"] == 0


def test_two_segments_are_both_packed_each_with_its_own_orientation(make_site, make_capacity, monkeypatch):
    """The Phase 3 fix itself: a roof with two planes gets panels on BOTH,
    each carrying its own azimuth/tilt/segmentIndex — never one shared
    orientation forced across a multi-plane roof."""
    site = make_site(boundary=_square_4326(40.0))
    usable_roof = compute_usable_roof(site)
    assert usable_roof.polygon_metric is not None

    # Two disjoint halves of the 40x40 roof, each its own plane, distinct
    # azimuths. A large target so both segments actually get filled.
    segments = [
        _segment(azimuth=90.0, pitch=10.0, bbox_side_m=20.0, offset_x=0.0, offset_y=0.0),
        _segment(azimuth=270.0, pitch=25.0, bbox_side_m=20.0, offset_x=20.0, offset_y=20.0),
    ]
    capacity = make_capacity(recommended_kwp=100.0)
    monkeypatch.setattr(
        router_module, "fetch_building_insights", lambda lat, lng: _insights(segments=segments)
    )

    layout, roof_segments, _warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    assert layout is not None
    assert layout["status"] == "ok"
    seen_segment_indices = {panel["segmentIndex"] for panel in layout["panels"]}
    assert seen_segment_indices == {0, 1}
    azimuths_by_segment = {panel["segmentIndex"]: panel["azimuthDeg"] for panel in layout["panels"]}
    assert azimuths_by_segment[0] == 90.0
    assert azimuths_by_segment[1] == 270.0
    assert roof_segments is not None
    assert len(roof_segments["segments"]) == 2
    assert roof_segments["segments"][0]["azimuthDeg"] == 90.0
    assert roof_segments["segments"][1]["azimuthDeg"] == 270.0
    # Step 14 — each segment's own polygon, for drawing distinct roof
    # planes on the map instead of only the shared boundary outline.
    for entry in roof_segments["segments"]:
        assert entry["polygon"] is not None
        assert len(entry["polygon"]) >= 4  # a closed ring, not a bare point/line
        assert entry["overlapAreaM2"] is not None and entry["overlapAreaM2"] > 0
    # The winning (most-panels) plane's own overlap area, for the
    # generation estimate's partial-coverage caveat — real and positive
    # here since a real overlapping plane was packed.
    assert roof_segments["primaryPlaneOverlapM2"] is not None
    assert roof_segments["primaryPlaneOverlapM2"] > 0


def test_metric_polygon_to_wgs84_ring_degrades_on_a_multipolygon():
    """A segment/usable-roof intersection can in principle produce a
    MultiPolygon on a re-entrant shape — drawing only one piece would
    misrepresent the plane, so this must report "no polygon" rather
    than silently picking a part."""
    from shapely.geometry import MultiPolygon
    from shapely.geometry import box as shapely_box2

    multi = MultiPolygon([shapely_box2(0, 0, 1, 1), shapely_box2(5, 5, 6, 6)])

    assert router_module._metric_polygon_to_wgs84_ring(multi, 32644) is None


def test_a_segment_is_skipped_when_its_bbox_does_not_overlap_the_usable_roof(
    make_site, make_capacity, monkeypatch
):
    """A segment whose reported bbox sits entirely outside this app's own
    resolved usable polygon contributes nothing — never panels floating
    off the actual roof."""
    site = make_site(boundary=_square_4326(20.0))
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=4.0)

    far_segment = _segment(bbox_side_m=10.0, offset_x=1000.0, offset_y=1000.0)
    monkeypatch.setattr(
        router_module,
        "fetch_building_insights",
        lambda lat, lng: _insights(segments=[far_segment]),
    )

    layout, segments, _warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    assert layout is not None
    assert layout["status"] == "no_layout"
    assert segments is not None  # segment metadata is still recorded
    # Zero real overlap with the customer's own resolved boundary — the
    # figure engine/fitness.py::_aggregate_geometry_confidence() now
    # weights by, instead of this segment's raw (irrelevant) Google area.
    assert segments["segments"][0]["overlapAreaM2"] == 0.0
    assert segments["segments"][0]["polygon"] is None


def test_a_crop_covering_only_part_of_a_segment_reports_the_clipped_overlap_not_googles_full_area(
    make_site, make_capacity, monkeypatch
):
    """The exact scenario this fix targets: the customer's crop is a
    SMALL polygon that only partially overlaps a much LARGER Google
    segment. overlapAreaM2 must reflect the small clipped intersection,
    never Google's full segment bbox area — otherwise the confidence
    weighting downstream would treat the whole (mostly un-selected)
    Google segment as if the customer had selected it."""
    # A small 10x10 crop...
    site = make_site(boundary=_square_4326(10.0))
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=4.0)

    # ...but Google's own segment bbox is a much bigger 100x100 area,
    # only overlapping roughly the crop's own corner.
    huge_segment = _segment(bbox_side_m=100.0, offset_x=0.0, offset_y=0.0, area=10000.0)
    monkeypatch.setattr(
        router_module,
        "fetch_building_insights",
        lambda lat, lng: _insights(segments=[huge_segment]),
    )

    _layout, roof_segments, _warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    entry = roof_segments["segments"][0]
    # Google's raw, unclipped metadata stays as-is (legitimate to keep
    # as descriptive metadata) ...
    assert entry["areaM2"] == 10000.0
    # ...but the real overlap is bounded by the crop's own 10x10=100 m^2
    # extent, nowhere near Google's full 10000 m^2 segment.
    assert entry["overlapAreaM2"] is not None
    assert 0 < entry["overlapAreaM2"] <= 100.0
    assert entry["overlapAreaM2"] < entry["areaM2"]


# ---------------------------------------------------------------------------
# overlapAreaM2 regression matrix — every crop/segment geometric
# relationship the confidence fix (engine/fitness.py::_aggregate_geometry_
# confidence()) needs to be right about. Each case asserts the exact
# clipped-overlap area, never Google's raw segment area.
# ---------------------------------------------------------------------------


def test_crop_fully_inside_googles_segment_overlap_equals_the_whole_crop(make_site, make_capacity, monkeypatch):
    """Scenario 1. Google segment 500 m^2 (declared), user crop ~100 m^2
    before AREA-01's own edge setback shrinks it — usable_roof.
    polygon_metric.area is the real, post-setback shape _segment_
    polygon_metric() actually intersects against (usable_roof.area_m2
    is smaller still, additionally derated by AREA-05's utilisation
    factor, so it's not the right comparison here). overlapAreaM2 must
    equal that whole usable polygon, not the segment's 500 m^2 declared
    area."""
    site = make_site(boundary=_square_4326(10.0))  # ~10x10 crop, before setback
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=4.0)

    segment = _segment(area=500.0, bbox_side_m=50.0, offset_x=0.0, offset_y=0.0)  # bbox fully contains the crop
    monkeypatch.setattr(router_module, "fetch_building_insights", lambda lat, lng: _insights(segments=[segment]))

    _layout, roof_segments, _warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    entry = roof_segments["segments"][0]
    assert entry["areaM2"] == 500.0  # Google's raw metadata, kept as reference
    # The whole usable crop — never Google's 500 m^2, and strictly less
    # than it (proof the segment's own size never leaks in).
    assert entry["overlapAreaM2"] == pytest.approx(usable_roof.polygon_metric.area, rel=0.01)
    assert entry["overlapAreaM2"] < entry["areaM2"]


def test_crop_partially_overlapping_googles_segment_overlap_is_just_the_shared_area(
    make_site, make_capacity, monkeypatch
):
    """Scenario 2. Crop and segment overlap only at a shared corner —
    overlapAreaM2 must equal just that shared region, not the crop's
    full area and not the segment's full area."""
    site = make_site(boundary=_square_4326(10.0, offset_x=0.0, offset_y=0.0))  # 100 m^2 crop
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=4.0)

    # Segment's bbox is offset so only its bottom-left corner overlaps the crop.
    segment = _segment(area=100.0, bbox_side_m=10.0, offset_x=5.0, offset_y=5.0)
    monkeypatch.setattr(router_module, "fetch_building_insights", lambda lat, lng: _insights(segments=[segment]))

    _layout, roof_segments, _warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    entry = roof_segments["segments"][0]
    # A real, partial, non-trivial overlap — strictly less than both the
    # segment's own declared area AND the whole usable crop, never equal
    # to either (proof it's the actual clipped shared region, not a
    # stand-in for one or the other).
    assert 0 < entry["overlapAreaM2"] < entry["areaM2"]
    assert 0 < entry["overlapAreaM2"] < usable_roof.area_m2


def test_crop_smaller_than_segment_off_centre_overlap_still_equals_the_whole_crop(
    make_site, make_capacity, monkeypatch
):
    """Scenario 3. A smaller crop sitting inside (but not cornering) a
    larger segment — same "fully contained" outcome as scenario 1, via a
    different geometric arrangement, to guard against a fix that only
    happens to work for corner-aligned shapes."""
    site = make_site(boundary=_square_4326(10.0, offset_x=15.0, offset_y=15.0))  # 100 m^2, centred inside
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=4.0)

    segment = _segment(area=1600.0, bbox_side_m=40.0, offset_x=0.0, offset_y=0.0)  # spans (0,0)-(40,40)
    monkeypatch.setattr(router_module, "fetch_building_insights", lambda lat, lng: _insights(segments=[segment]))

    _layout, roof_segments, _warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    entry = roof_segments["segments"][0]
    assert entry["overlapAreaM2"] == pytest.approx(usable_roof.polygon_metric.area, rel=0.01)
    assert entry["overlapAreaM2"] < entry["areaM2"]


def test_crop_matching_segment_exactly_overlap_equals_the_whole_usable_crop(make_site, make_capacity, monkeypatch):
    """Scenario 4. Crop and segment declare the same shape/size/location
    — the matching Google data is legitimate supporting evidence here,
    and overlapAreaM2 correctly equals the whole usable crop, bounded by
    (never exceeding) Google's own declared segment area."""
    site = make_site(boundary=_square_4326(20.0, offset_x=0.0, offset_y=0.0))  # ~20x20 crop, before setback
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=4.0)

    segment = _segment(area=400.0, bbox_side_m=20.0, offset_x=0.0, offset_y=0.0)
    monkeypatch.setattr(router_module, "fetch_building_insights", lambda lat, lng: _insights(segments=[segment]))

    _layout, roof_segments, _warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    entry = roof_segments["segments"][0]
    assert entry["overlapAreaM2"] == pytest.approx(usable_roof.polygon_metric.area, rel=0.01)
    assert entry["overlapAreaM2"] <= entry["areaM2"]


def test_crop_with_no_overlap_reports_zero_and_is_excluded_from_confidence(
    make_site, make_capacity, monkeypatch
):
    """Scenario 5. Segment nowhere near the crop — overlapAreaM2 is
    exactly 0.0 (already covered by test_a_segment_is_skipped_when_its_
    bbox_does_not_overlap_the_usable_roof above; restated here to keep
    the full 6-scenario matrix in one place per the requested regression
    coverage)."""
    site = make_site(boundary=_square_4326(10.0))
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=4.0)

    segment = _segment(area=500.0, bbox_side_m=10.0, offset_x=1000.0, offset_y=1000.0)
    monkeypatch.setattr(router_module, "fetch_building_insights", lambda lat, lng: _insights(segments=[segment]))

    _layout, roof_segments, _warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    entry = roof_segments["segments"][0]
    assert entry["overlapAreaM2"] == 0.0
    assert entry["polygon"] is None


def test_multiple_segments_near_the_pin_only_the_overlapping_ones_get_real_overlap(
    make_site, make_capacity, monkeypatch
):
    """Scenario 6. Several Google segments detected near the original
    pin — two overlap the crop (to different degrees), one doesn't
    overlap at all. Each segment's overlapAreaM2 must reflect ONLY its
    own real intersection with the crop, independent of the others."""
    site = make_site(boundary=_square_4326(40.0, offset_x=0.0, offset_y=0.0))  # 1600 m^2 crop
    usable_roof = compute_usable_roof(site)
    capacity = make_capacity(recommended_kwp=20.0)

    segment_fully_inside = _segment(
        azimuth=90.0, area=400.0, bbox_side_m=20.0, offset_x=0.0, offset_y=0.0
    )  # entirely within the crop
    segment_partial = _segment(
        azimuth=180.0, area=900.0, bbox_side_m=30.0, offset_x=25.0, offset_y=25.0
    )  # only its bottom-left corner overlaps the crop
    segment_far_away = _segment(
        azimuth=270.0, area=200.0, bbox_side_m=10.0, offset_x=1000.0, offset_y=1000.0
    )  # nowhere near the crop
    monkeypatch.setattr(
        router_module,
        "fetch_building_insights",
        lambda lat, lng: _insights(segments=[segment_fully_inside, segment_partial, segment_far_away]),
    )

    _layout, roof_segments, _warning = router_module._pack_panel_layout(
        usable_roof, capacity, _ORIGIN_LAT, _ORIGIN_LON
    )

    by_index = {entry["segmentIndex"]: entry for entry in roof_segments["segments"]}
    assert 0 < by_index[0]["overlapAreaM2"] <= 400.0  # within the crop — bounded by its own 20x20 bbox
    assert 0 < by_index[1]["overlapAreaM2"] < 900.0  # partial — less than its own declared area
    assert by_index[2]["overlapAreaM2"] == 0.0  # far away — none at all
    # And the confidence aggregate built from this exact roof_segments
    # dict only reflects the two overlapping segments' clipped areas —
    # the far-away segment's 200 m^2 contributes nothing.
    from solarfit.engine.fitness import _aggregate_geometry_confidence

    confidence_with_all_three = _aggregate_geometry_confidence(site, roof_segments)
    roof_segments_without_far = {
        "segments": [s for s in roof_segments["segments"] if s["segmentIndex"] != 2]
    }
    confidence_without_far = _aggregate_geometry_confidence(site, roof_segments_without_far)
    assert confidence_with_all_three == pytest.approx(confidence_without_far, abs=1e-9)
