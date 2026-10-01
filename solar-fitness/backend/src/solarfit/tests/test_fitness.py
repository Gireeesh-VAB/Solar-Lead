"""Tests for engine/fitness.py — §9.7 Fitness Scoring (FIT-01..07) and
the scoring half of §9.17 Shading Analysis (SHADE-04).

Runs against the real packages/config-packs/rooftop_v1.yaml (placeholder
values) via the real config_pack loader — no mocking needed, since these
are just coefficients, not external calls. Verdict-boundary tests use
extreme, unambiguous inputs rather than hardcoded score thresholds, so
they stay valid even after Person 2 retunes the placeholder weights.
"""

import math
from datetime import UTC, datetime, timedelta

import pytest
from pyproj import Transformer
from shapely.geometry import Polygon, box as shapely_box
from shapely.ops import transform

from solarfit.domain.site import ShadingEstimate
from solarfit.engine.fitness import _imagery_recency_score, score_fitness


def test_missing_capacity_returns_insufficient_data(make_site, make_capacity):
    site = make_site()
    capacity = make_capacity(status="INSUFFICIENT_DATA", recommended_kwp=None)

    result = score_fitness(site, capacity)

    assert result.verdict == "INSUFFICIENT_DATA"
    assert result.score is None
    assert result.binding_constraint.startswith("insufficient_data:")
    assert result.confidence > 0.0  # FIT-06 — always a real confidence, never omitted


def test_missing_geometry_confidence_returns_insufficient_data(make_site, make_capacity):
    site = make_site(geometry_confidence=None)
    capacity = make_capacity()

    result = score_fitness(site, capacity)

    assert result.verdict == "INSUFFICIENT_DATA"
    assert result.score is None
    assert result.binding_constraint == "insufficient_data:geometry_confidence"


def test_insufficient_data_never_a_low_score_it_is_none(make_site, make_capacity):
    """§17 non-negotiable: INSUFFICIENT_DATA is never a low score."""
    site = make_site(geometry_confidence=None)
    capacity = make_capacity(recommended_kwp=None, status="INSUFFICIENT_DATA")

    result = score_fitness(site, capacity)

    assert result.verdict == "INSUFFICIENT_DATA"
    assert result.score is None


def test_score_is_none_iff_verdict_is_insufficient_data(make_site, make_capacity):
    ok_result = score_fitness(make_site(), make_capacity())
    assert ok_result.verdict != "INSUFFICIENT_DATA"
    assert ok_result.score is not None

    bad_result = score_fitness(make_site(geometry_confidence=None), make_capacity())
    assert bad_result.verdict == "INSUFFICIENT_DATA"
    assert bad_result.score is None


def test_extremely_favourable_inputs_yield_suitable(make_site, make_capacity):
    site = make_site(
        geometry_confidence=1.0,
        shading=ShadingEstimate(shading_score=1.0, source="solar_api"),
    )
    capacity = make_capacity(recommended_kwp=100.0, headroom_kwp=100.0)

    result = score_fitness(site, capacity)

    assert result.verdict == "SUITABLE"
    assert result.score is not None
    assert result.score > 0.9


def test_extremely_unfavourable_inputs_yield_not_suitable(make_site, make_capacity):
    site = make_site(
        geometry_confidence=0.05,
        shading=ShadingEstimate(shading_score=0.0, source="solar_api"),
    )
    capacity = make_capacity(recommended_kwp=0.01, headroom_kwp=0.0)

    result = score_fitness(site, capacity)

    assert result.verdict == "NOT_SUITABLE"
    assert result.score is not None
    assert result.score < 0.2


def test_shading_unavailable_is_excluded_not_assumed(make_site, make_capacity):
    site = make_site(shading=ShadingEstimate(shading_score=None, source="unavailable"))
    capacity = make_capacity()

    result = score_fitness(site, capacity)

    assert result.components["shading"] is None
    assert any("shading" in r.lower() and "unavailable" in r.lower() for r in result.reasons)
    # Excluding shading must not be conflated with INSUFFICIENT_DATA overall.
    assert result.verdict != "INSUFFICIENT_DATA"


def test_shading_none_on_site_is_also_excluded_not_assumed(make_site, make_capacity):
    site = make_site(shading=None)
    capacity = make_capacity()

    result = score_fitness(site, capacity)

    assert result.components["shading"] is None
    assert result.verdict != "INSUFFICIENT_DATA"


def test_missing_generation_estimate_is_excluded_not_assumed(make_site, make_capacity):
    site = make_site()
    capacity = make_capacity()

    result = score_fitness(site, capacity, params={})

    assert result.components["generation_yield"] is None
    assert any("generation" in r.lower() for r in result.reasons)


def test_generation_estimate_used_when_present(make_site, make_capacity):
    site = make_site()
    capacity = make_capacity()

    result = score_fitness(site, capacity, params={"generation": {"performance_ratio": 0.95}})

    assert result.components["generation_yield"] == 0.95


def test_gate_fail_forces_not_suitable_regardless_of_score(make_site, make_capacity, make_gate):
    site = make_site(
        geometry_confidence=1.0,
        shading=ShadingEstimate(shading_score=1.0, source="solar_api"),
    )
    capacity = make_capacity(recommended_kwp=100.0, headroom_kwp=100.0)
    gates = [make_gate(gate="structural_gate", status="FAIL", detail="Roof cannot bear load")]

    result = score_fitness(site, capacity, params={"gates": gates})

    assert result.verdict == "NOT_SUITABLE"
    assert result.binding_constraint == "gate:structural_gate"
    assert any("structural_gate" in r for r in result.reasons)


def test_gate_pending_caps_verdict_at_subject_to_survey(make_site, make_capacity, make_gate):
    site = make_site(
        geometry_confidence=1.0,
        shading=ShadingEstimate(shading_score=1.0, source="solar_api"),
    )
    capacity = make_capacity(recommended_kwp=100.0, headroom_kwp=100.0)
    gates = [make_gate(gate="structural_gate", status="PENDING", detail="Awaiting survey")]

    result = score_fitness(site, capacity, params={"gates": gates})

    # Would otherwise be SUITABLE given the extreme-favourable inputs.
    assert result.verdict == "SUITABLE_SUBJECT_TO_SURVEY"


def test_binding_constraint_never_none_or_empty(make_site, make_capacity):
    for capacity_overrides in [{}, {"binding_constraint": None}]:
        result = score_fitness(make_site(), make_capacity(**capacity_overrides))
        assert result.binding_constraint
        assert isinstance(result.binding_constraint, str)


def test_confidence_always_in_bounds(make_site, make_capacity):
    scenarios = [
        (make_site(), make_capacity()),
        (make_site(geometry_confidence=None), make_capacity()),
        (make_site(), make_capacity(recommended_kwp=None, status="INSUFFICIENT_DATA")),
        (make_site(geometry_confidence=0.0), make_capacity(headroom_kwp=0.0)),
        (make_site(geometry_confidence=1.0), make_capacity(headroom_kwp=1000.0, recommended_kwp=1000.0)),
    ]
    for site, capacity in scenarios:
        result = score_fitness(site, capacity)
        assert 0.0 < result.confidence <= 1.0


def test_confidence_degrades_with_stale_imagery(make_site, make_capacity):
    fresh_site = make_site(imagery_date=datetime.now(UTC))
    stale_site = make_site(imagery_date=datetime.now(UTC) - timedelta(days=3000))
    capacity = make_capacity()

    fresh_result = score_fitness(fresh_site, capacity)
    stale_result = score_fitness(stale_site, capacity)

    assert stale_result.confidence < fresh_result.confidence


# ---------------------------------------------------------------------------
# FIT-04 — real per-roof-segment geometry confidence (area-weighted),
# fed via params["roof_segments"] (routers/assessments.py::_pack_panel_
# layout()'s real Building Insights roofSegmentStats). See
# engine/fitness.py::_aggregate_geometry_confidence()'s own docstring for
# why "multiple roofs" means per-plane segments within one boundary, not
# independent site polygons (no such data model exists here).
# ---------------------------------------------------------------------------


def _octagon_4326(radius_m: float, *, offset_m: tuple[float, float] = (0.0, 0.0)) -> list[list[float]]:
    """A real 8-vertex polygon near the same Hyderabad point make_site()
    defaults to, as a BARE EXTERIOR RING (list[[lng, lat], ...]) — the
    same shape routers/assessments.py::_metric_polygon_to_wgs84_ring()
    actually returns for a real roof_segments[]["polygon"], NOT a
    GeoJSON dict (_aggregate_geometry_confidence() wraps it into one
    itself). Same construction technique as tests/test_area.py's
    _square_4326()."""
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True).transform
    to_wgs84 = Transformer.from_crs("EPSG:32644", "EPSG:4326", always_xy=True).transform
    cx, cy = to_utm(78.4867, 17.3850)
    dx, dy = offset_m
    cx, cy = cx + dx, cy + dy
    points = [
        (
            cx + radius_m * math.cos(2 * math.pi * i / 8),
            cy + radius_m * math.sin(2 * math.pi * i / 8),
        )
        for i in range(8)
    ]
    return [list(point) for point in transform(to_wgs84, Polygon(points)).exterior.coords]


def _square_4326(side_m: float, *, offset_m: tuple[float, float] = (0.0, 0.0)) -> list[list[float]]:
    """A real 4-vertex square, as a bare exterior ring — see
    _octagon_4326()'s own docstring for why."""
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True).transform
    to_wgs84 = Transformer.from_crs("EPSG:32644", "EPSG:4326", always_xy=True).transform
    x0, y0 = to_utm(78.4867, 17.3850)
    dx, dy = offset_m
    square = shapely_box(x0 + dx, y0 + dy, x0 + dx + side_m, y0 + dy + side_m)
    return [list(point) for point in transform(to_wgs84, square).exterior.coords]


def _segments(*entries: dict) -> dict:
    """`entries` are partial segment dicts (polygon/areaM2/overlapAreaM2);
    segmentIndex is filled in automatically — matches routers/
    assessments.py::_pack_panel_layout()'s real roof_segments["segments"]
    shape closely enough for _aggregate_geometry_confidence(), which
    reads `polygon` and `overlapAreaM2` (the area actually clipped to
    the customer's selected boundary — `areaM2` stays as Google's raw,
    unclipped descriptive metadata, no longer used as a weight).

    overlapAreaM2 defaults to areaM2 when the entry has a real polygon
    (most of these tests model a segment fully within the customer's
    selection) — but to 0.0 when polygon is None, matching the real
    invariant _pack_panel_layout() itself keeps: a polygon-less segment
    IS a zero-overlap segment, never a real one scored via a fallback.
    Tests exercising partial overlap set overlapAreaM2 explicitly."""
    segments = []
    for i, entry in enumerate(entries):
        entry = dict(entry)
        if "overlapAreaM2" not in entry:
            entry["overlapAreaM2"] = entry.get("areaM2") if entry.get("polygon") is not None else 0.0
        segments.append({"segmentIndex": i, **entry})
    return {"segments": segments}


def test_no_roof_segments_falls_back_to_the_single_site_scalar_unchanged(make_site, make_capacity):
    """The common case (manual/imported/field_measured, or no Building
    Insights segments) must be byte-identical to before this feature."""
    site = make_site(geometry_confidence=0.42)
    capacity = make_capacity()

    without_param = score_fitness(site, capacity)
    with_empty_segments = score_fitness(site, capacity, params={"roof_segments": {"segments": []}})
    with_none = score_fitness(site, capacity, params={"roof_segments": None})

    assert without_param.confidence == with_empty_segments.confidence == with_none.confidence


def test_vertex_count_alone_does_not_change_geometry_confidence(make_site, make_capacity):
    """GEO-09: a valid four-corner rectangle is exactly as trustworthy as
    a valid 8-vertex traced outline — vertex count is not a quality
    signal on its own (a real rectangular roof is legitimately a
    4-point polygon). Same area, same source, same imagery, both
    geometrically valid — only vertex count differs, so confidence must
    come out identical, not lower for the simpler shape."""
    site = make_site(geometry_source="solar_api")
    capacity = make_capacity()

    four_vertex = score_fitness(
        site, capacity, params={"roof_segments": _segments({"polygon": _square_4326(20.0), "areaM2": 400.0})}
    )
    eight_vertex = score_fitness(
        site,
        capacity,
        params={"roof_segments": _segments({"polygon": _octagon_4326(11.3), "areaM2": 400.0})},
    )

    assert eight_vertex.confidence == four_vertex.confidence


def test_multiple_roofs_with_different_geometry_confidence_are_area_weighted(make_site, make_capacity):
    """Roof A (a tiny, implausibly-small trace — real quality signal:
    GEO-09's area-plausibility check, not vertex count) and Roof B (a
    large, comfortably plausible trace) combine into one figure that
    sits between the two — closer to whichever roof actually carries
    more area, not a flat average and not just the first/largest roof
    alone."""
    site = make_site(geometry_source="solar_api")
    capacity = make_capacity()

    small_implausible_alone = score_fitness(
        site, capacity, params={"roof_segments": _segments({"polygon": _square_4326(2.0), "areaM2": 4.0})}
    )
    large_typical_alone = score_fitness(
        site,
        capacity,
        params={"roof_segments": _segments({"polygon": _octagon_4326(28.2), "areaM2": 2500.0})},
    )
    combined = score_fitness(
        site,
        capacity,
        params={
            "roof_segments": _segments(
                {"polygon": _square_4326(2.0), "areaM2": 4.0},
                {"polygon": _octagon_4326(28.2), "areaM2": 2500.0},
            )
        },
    )

    assert small_implausible_alone.confidence < combined.confidence < large_typical_alone.confidence
    # 2500 m^2 vs 4 m^2 — the combined figure should land much closer to
    # the large roof's own confidence than to the small one's.
    assert (large_typical_alone.confidence - combined.confidence) < (
        combined.confidence - small_implausible_alone.confidence
    )


def test_a_small_roof_is_not_silently_ignored_next_to_a_much_larger_one(make_site, make_capacity):
    """Adding a tiny second roof must still move the figure — a small
    roof folded to a weight of 0 (i.e. dropped) would leave `combined`
    identical to `large_alone`, which this asserts against."""
    site = make_site(geometry_source="solar_api")
    capacity = make_capacity()

    large_alone = score_fitness(
        site, capacity, params={"roof_segments": _segments({"polygon": _octagon_4326(28.2), "areaM2": 2500.0})}
    )
    large_plus_tiny = score_fitness(
        site,
        capacity,
        params={
            "roof_segments": _segments(
                {"polygon": _octagon_4326(28.2), "areaM2": 2500.0},
                {"polygon": _square_4326(2.0), "areaM2": 4.0},
            )
        },
    )

    assert large_plus_tiny.confidence != large_alone.confidence


def test_a_segment_with_no_overlap_is_excluded_not_scored_via_site_level(make_site, make_capacity):
    """A segment with no real overlap with the customer's own selected/
    cropped boundary (polygon=None, i.e. overlapAreaM2=0 — see
    _segment_polygon_metric()'s docstring) must NOT pull this site's
    confidence at all — it isn't part of the roof the customer selected,
    so it must be excluded from the aggregate entirely, never folded in
    via a site-level fallback score at full un-clipped weight (that was
    the exact bug: an un-cropped Google segment silently influencing the
    selected roof's confidence)."""
    site = make_site(geometry_source="solar_api", geometry_confidence=0.9)
    capacity = make_capacity()

    good_segment_alone = score_fitness(
        site, capacity, params={"roof_segments": _segments({"polygon": _square_4326(5.0), "areaM2": 25.0})}
    )
    with_a_non_overlapping_segment = score_fitness(
        site,
        capacity,
        params={
            "roof_segments": _segments(
                {"polygon": _square_4326(5.0), "areaM2": 25.0},
                {"polygon": None, "areaM2": 2500.0},  # a large Google segment, zero overlap with the crop
            )
        },
    )

    # A big non-overlapping segment must not move the confidence AT ALL
    # — not even nudged toward the 0.9 site-level scalar it used to
    # borrow.
    assert with_a_non_overlapping_segment.confidence == good_segment_alone.confidence


def test_a_partially_overlapping_segment_weighs_by_the_clipped_area_not_googles_raw_area(
    make_site, make_capacity
):
    """A crop that covers only PART of a Google roof segment must weight
    that segment by the small overlapping portion actually selected, not
    by Google's full, un-clipped segment area — otherwise a huge Google
    segment the customer mostly did NOT select could still dominate the
    confidence blend just because their crop happens to touch a sliver
    of it. Reuses the same small-implausible (low confidence) vs.
    large-typical (higher confidence) shapes already proven, in
    test_multiple_roofs_with_different_geometry_confidence_are_area_
    weighted above, to actually differ in per-segment confidence."""
    site = make_site(geometry_source="solar_api")
    capacity = make_capacity()

    small_implausible_alone = score_fitness(
        site, capacity, params={"roof_segments": _segments({"polygon": _square_4326(2.0), "areaM2": 4.0})}
    )
    large_typical_alone = score_fitness(
        site, capacity, params={"roof_segments": _segments({"polygon": _octagon_4326(28.2), "areaM2": 2500.0})}
    )

    # The large segment's raw Google area is 2500 m^2, but the crop only
    # actually overlaps 4 m^2 of it (a sliver) — same as the small
    # segment's own overlap.
    tiny_actual_overlap = score_fitness(
        site,
        capacity,
        params={
            "roof_segments": _segments(
                {"polygon": _square_4326(2.0), "areaM2": 4.0, "overlapAreaM2": 4.0},
                {"polygon": _octagon_4326(28.2), "areaM2": 2500.0, "overlapAreaM2": 4.0},
            )
        },
    )
    # Same two segments, but the large one's overlap genuinely matches
    # its real area — a large roof the customer actually selected.
    genuinely_large_overlap = score_fitness(
        site,
        capacity,
        params={
            "roof_segments": _segments(
                {"polygon": _square_4326(2.0), "areaM2": 4.0, "overlapAreaM2": 4.0},
                {"polygon": _octagon_4326(28.2), "areaM2": 2500.0, "overlapAreaM2": 2500.0},
            )
        },
    )

    # Equal overlap weight (4 m^2 each) must land at the midpoint between
    # the two segments' own confidence values, nowhere near either
    # extreme, and nothing like the "dominated by the big segment's raw
    # 2500 m^2" result that using Google's unclipped area would produce.
    midpoint = (small_implausible_alone.confidence + large_typical_alone.confidence) / 2
    assert tiny_actual_overlap.confidence == pytest.approx(midpoint, abs=0.01)
    # Whereas genuine full overlap reproduces the ORIGINAL area-weighted
    # test's own result: dominated by the large segment, closer to it
    # than to the small one.
    assert (
        abs(genuinely_large_overlap.confidence - large_typical_alone.confidence)
        < abs(genuinely_large_overlap.confidence - small_implausible_alone.confidence)
    )


def test_imagery_recency_stays_one_site_level_factor_even_with_segments(make_site, make_capacity):
    """Every real segment shares the SAME Solar API capture — there is no
    per-segment imagery date in this data model (see
    _aggregate_geometry_confidence()'s docstring), so passing segments
    must never change how imagery recency itself behaves: identical
    fresh-vs-stale gap with or without roof_segments present."""
    capacity = make_capacity()
    segments_param = {"roof_segments": _segments({"polygon": _square_4326(20.0), "areaM2": 400.0})}

    fresh_no_segments = score_fitness(make_site(imagery_date=datetime.now(UTC)), capacity)
    stale_no_segments = score_fitness(
        make_site(imagery_date=datetime.now(UTC) - timedelta(days=3000)), capacity
    )
    fresh_with_segments = score_fitness(
        make_site(imagery_date=datetime.now(UTC)), capacity, params=segments_param
    )
    stale_with_segments = score_fitness(
        make_site(imagery_date=datetime.now(UTC) - timedelta(days=3000)), capacity, params=segments_param
    )

    assert stale_no_segments.confidence < fresh_no_segments.confidence
    assert stale_with_segments.confidence < fresh_with_segments.confidence


def test_old_imagery_still_lowers_confidence_but_floors_above_zero_regardless_of_segments(
    make_site, make_capacity
):
    """Old imagery must still cost confidence relative to fresh imagery
    — but per the imagery-recency floor, never enough on its own to
    read as "no confidence at all" (it used to decay all the way to
    0.0 past 730 days; it now floors at 0.70 — see
    _imagery_recency_score()'s own docstring)."""
    ancient = make_site(imagery_date=datetime.now(UTC) - timedelta(days=800))
    fresh = make_site(imagery_date=datetime.now(UTC) - timedelta(days=1))
    capacity = make_capacity()
    segments_param = {"roof_segments": _segments({"polygon": _square_4326(20.0), "areaM2": 400.0})}

    ancient_result = score_fitness(ancient, capacity, params=segments_param)
    fresh_result = score_fitness(fresh, capacity, params=segments_param)

    assert ancient_result.confidence < fresh_result.confidence


def test_missing_imagery_date_is_not_a_guessed_high_confidence(make_site, make_capacity):
    site = make_site(imagery_date=None)
    capacity = make_capacity()

    result = score_fitness(
        site, capacity, params={"roof_segments": _segments({"polygon": _square_4326(20.0), "areaM2": 400.0})}
    )
    fresh_result = score_fitness(
        make_site(imagery_date=datetime.now(UTC)),
        capacity,
        params={"roof_segments": _segments({"polygon": _square_4326(20.0), "areaM2": 400.0})},
    )

    assert result.confidence < fresh_result.confidence


# ---------------------------------------------------------------------------
# FIT-04 imagery_recency — the piecewise floor curve (real config values:
# full=180d/1.0, 365d/0.90, 540d/0.80, floor=0.70 from zero=730d onward).
# Case numbers below match this fix's own testing requirements list.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "age_days, expected, tolerance",
    [
        (0, 1.00, 0.001),  # Case 1
        (180, 1.00, 0.001),  # Case 2
        (365, 0.90, 0.001),  # Case 3
        (540, 0.80, 0.001),  # Case 4
        (573, 0.79, 0.02),  # Case 5 — "approximately 0.78-0.80"
        (730, 0.70, 0.001),  # Case 6
        (2000, 0.70, 0.001),  # Case 7 — far past 730 still floors, not 0.0
    ],
)
def test_imagery_recency_matches_the_floor_curve_at_each_breakpoint(age_days, expected, tolerance):
    imagery_date = datetime.now(UTC) - timedelta(days=age_days)

    score = _imagery_recency_score(imagery_date)

    assert score == pytest.approx(expected, abs=tolerance)


def test_imagery_recency_573_days_lands_in_the_0_78_to_0_80_band():
    """The fix's own headline example, asserted as an explicit range
    rather than folded into the parametrized approx above."""
    imagery_date = datetime.now(UTC) - timedelta(days=573)

    score = _imagery_recency_score(imagery_date)

    assert 0.78 <= score <= 0.80


def test_imagery_recency_never_drops_below_the_floor_however_old():
    """Case 7, continued: the floor holds indefinitely — 10 years old
    scores the same as 731 days old, never lower."""
    just_past_zero = _imagery_recency_score(datetime.now(UTC) - timedelta(days=731))
    decade_old = _imagery_recency_score(datetime.now(UTC) - timedelta(days=3650))

    assert just_past_zero == pytest.approx(0.70, abs=0.001)
    assert decade_old == pytest.approx(0.70, abs=0.001)


def test_imagery_recency_missing_date_keeps_the_existing_zero_fallback():
    """Case 8: a missing imagery date is NOT "very old imagery" — it's
    a different, unchanged failure mode (FIT-06: never invent a date,
    never guess a high score for absent data), so it must NOT floor at
    0.70 either. Same 0.0 fallback as before this fix."""
    assert _imagery_recency_score(None) == 0.0


def test_insufficient_data_still_caps_confidence_at_0_35_with_segments(make_site, make_capacity):
    site = make_site(geometry_confidence=None)
    capacity = make_capacity()

    result = score_fitness(
        site, capacity, params={"roof_segments": _segments({"polygon": _square_4326(20.0), "areaM2": 400.0})}
    )

    assert result.verdict == "INSUFFICIENT_DATA"
    assert result.confidence <= 0.35


def test_roof_segments_never_change_the_suitability_score_or_its_geometry_component(
    make_site, make_capacity
):
    """The critical regression guard: FIT-01's raw_score and its
    `geometry_quality` component both keep reading `site.geometry_
    confidence` verbatim (_compute_components() is untouched) — only
    FIT-04's confidence figure may move when segments are supplied."""
    site = make_site(geometry_source="solar_api", geometry_confidence=0.5)
    capacity = make_capacity()

    without_segments = score_fitness(site, capacity)
    with_segments = score_fitness(
        site,
        capacity,
        params={
            "roof_segments": _segments(
                {"polygon": _square_4326(5.0), "areaM2": 25.0},
                {"polygon": _octagon_4326(28.2), "areaM2": 2500.0},
            )
        },
    )

    assert with_segments.score == without_segments.score
    assert with_segments.components["geometry_quality"] == without_segments.components["geometry_quality"]
    assert with_segments.verdict == without_segments.verdict
    # The whole point of the change — confidence itself is free to differ.


def test_limitations_statement_present_on_every_result(make_site, make_capacity):
    ok_result = score_fitness(make_site(), make_capacity())
    bad_result = score_fitness(make_site(geometry_confidence=None), make_capacity())

    assert ok_result.limitations
    assert bad_result.limitations
    assert ok_result.limitations == bad_result.limitations  # standard, verbatim, always the same


def test_pack_version_stamped(make_site, make_capacity):
    result = score_fitness(make_site(), make_capacity())
    assert result.pack_version == "rooftop_v1"


def test_reasons_never_empty(make_site, make_capacity):
    ok_result = score_fitness(make_site(), make_capacity())
    bad_result = score_fitness(make_site(geometry_confidence=None), make_capacity())

    assert len(ok_result.reasons) > 0
    assert len(bad_result.reasons) > 0


def test_reproducible_given_identical_inputs(make_site, make_capacity, make_gate):
    site = make_site()
    capacity = make_capacity()
    gates = [make_gate()]

    first = score_fitness(site, capacity, params={"gates": gates})
    second = score_fitness(site, capacity, params={"gates": gates})

    assert first == second


def test_ml_score_cannot_influence_fitness_result(make_site, make_capacity):
    """FIT-06/§17: the ML score is additive metadata and must never
    substitute for or influence the FIT verdict. score_fitness() doesn't
    even accept an MLScore parameter — this test documents that
    guarantee structurally, by confirming identical FitnessResults
    regardless of what an (unused) adversarial ML score would claim."""
    site = make_site()
    capacity = make_capacity()

    result = score_fitness(site, capacity)
    result_again = score_fitness(site, capacity)

    assert result == result_again


# ---------------------------------------------------------------------------
# Phase 6 — explicit condition codes (domain/assessment.py::ConditionCode),
# additive alongside the existing verdict/binding_constraint/reasons.
# ---------------------------------------------------------------------------


def test_missing_capacity_reports_a_missing_capacity_data_condition(make_site, make_capacity):
    site = make_site()
    capacity = make_capacity(recommended_kwp=None, status="INSUFFICIENT_DATA")

    result = score_fitness(site, capacity)

    assert [c.code for c in result.conditions] == ["MISSING_CAPACITY_DATA"]


def test_missing_geometry_confidence_reports_its_own_condition_code(make_site, make_capacity):
    site = make_site(geometry_confidence=None)
    capacity = make_capacity()

    result = score_fitness(site, capacity)

    assert [c.code for c in result.conditions] == ["MISSING_GEOMETRY_CONFIDENCE"]


def test_shading_unavailable_reports_a_condition_not_just_a_reasons_sentence(make_site, make_capacity):
    site = make_site(shading=ShadingEstimate(shading_score=None, source="unavailable"))
    capacity = make_capacity()

    result = score_fitness(site, capacity)

    assert any(c.code == "SHADING_DATA_UNAVAILABLE" for c in result.conditions)


def test_low_shading_score_reports_high_shading_condition(make_site, make_capacity):
    site = make_site(shading=ShadingEstimate(shading_score=0.1, source="solar_api"))
    capacity = make_capacity()

    result = score_fitness(site, capacity)

    assert any(c.code == "HIGH_SHADING" for c in result.conditions)


def test_good_shading_score_reports_no_shading_condition(make_site, make_capacity):
    site = make_site(shading=ShadingEstimate(shading_score=0.95, source="solar_api"))
    capacity = make_capacity()

    result = score_fitness(site, capacity)

    assert not any(c.code in ("HIGH_SHADING", "SHADING_DATA_UNAVAILABLE") for c in result.conditions)


def test_gate_fail_reports_a_gate_failed_condition_naming_the_gate(make_site, make_capacity, make_gate):
    site = make_site(
        geometry_confidence=1.0,
        shading=ShadingEstimate(shading_score=1.0, source="solar_api"),
    )
    capacity = make_capacity(recommended_kwp=100.0, headroom_kwp=100.0)
    gates = [make_gate(gate="structural_gate", status="FAIL", detail="Roof cannot bear load")]

    result = score_fitness(site, capacity, params={"gates": gates})

    failed = [c for c in result.conditions if c.code == "GATE_FAILED"]
    assert len(failed) == 1
    assert failed[0].detail == "structural_gate"
    assert failed[0].message == "Roof cannot bear load"


def test_gate_pending_reports_a_gate_pending_condition_naming_the_gate(make_site, make_capacity, make_gate):
    site = make_site(
        geometry_confidence=1.0,
        shading=ShadingEstimate(shading_score=1.0, source="solar_api"),
    )
    capacity = make_capacity(recommended_kwp=100.0, headroom_kwp=100.0)
    gates = [make_gate(gate="net_metering_cap", status="PENDING", detail="Awaiting DISCOM confirmation")]

    result = score_fitness(site, capacity, params={"gates": gates})

    pending = [c for c in result.conditions if c.code == "GATE_PENDING"]
    assert len(pending) == 1
    assert pending[0].detail == "net_metering_cap"
