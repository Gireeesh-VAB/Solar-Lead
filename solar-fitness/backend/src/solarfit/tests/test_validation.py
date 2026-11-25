"""§9.2 Geometry Providers — GEO-07/GEO-09 (providers/validation.py).

No dedicated test file existed for this module before a spec-compliance
audit found two gaps here: GEO-07's plausibility/distance thresholds
were hard-coded Python constants rather than pack-sourced (CFG-01), and
GEO-09's confidence scoring never factored in area plausibility as a
graded input, only as validate_boundary's binary reject.

GEO-09's vertex-count penalty/bonus (-0.10 at <=4 vertices, +0.05 at
>=8) was removed in a later review: a legitimate rectangular roof is a
real 4-point polygon, and penalizing it for that — or rewarding a
polygon simply for having more points — never reflected actual
geometry quality. It's replaced by a geometry-VALIDITY check (parses,
is a Polygon, non-empty, not self-intersecting) — see the
test_case1../test_case7.. functions below for the coverage that
change needs.
"""

import math
from datetime import UTC, datetime

import pytest
from pyproj import Transformer
from shapely.geometry import Polygon, mapping
from shapely.geometry import box as shapely_box
from shapely.ops import transform

from solarfit.providers.validation import GeometryRejected, geometry_confidence, validate_boundary

ORIGIN_LON, ORIGIN_LAT = 78.4867, 17.3850
UTM44N = 32644


def _square_4326(side_m: float) -> dict:
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{UTM44N}", always_xy=True).transform
    to_wgs84 = Transformer.from_crs(f"EPSG:{UTM44N}", "EPSG:4326", always_xy=True).transform
    x0, y0 = to_utm(ORIGIN_LON, ORIGIN_LAT)
    square = shapely_box(x0, y0, x0 + side_m, y0 + side_m)
    return mapping(transform(to_wgs84, square))


def _octagon_4326(radius_m: float) -> dict:
    """A real, valid 8-vertex polygon with roughly the same area as
    _square_4326(radius_m * 1.85) — close enough for an "only vertex
    count differs" comparison, not exact-area-matched."""
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{UTM44N}", always_xy=True).transform
    to_wgs84 = Transformer.from_crs(f"EPSG:{UTM44N}", "EPSG:4326", always_xy=True).transform
    cx, cy = to_utm(ORIGIN_LON, ORIGIN_LAT)
    points = [
        (cx + radius_m * math.cos(2 * math.pi * i / 8), cy + radius_m * math.sin(2 * math.pi * i / 8))
        for i in range(8)
    ]
    return mapping(transform(to_wgs84, Polygon(points)))


def _l_shape_4326(side_m: float) -> dict:
    """A real, valid 6-vertex L-shaped polygon (a square with one corner
    bitten out) — a "multi-point, not a simple rectangle" boundary a
    customer might legitimately trace."""
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{UTM44N}", always_xy=True).transform
    to_wgs84 = Transformer.from_crs(f"EPSG:{UTM44N}", "EPSG:4326", always_xy=True).transform
    x0, y0 = to_utm(ORIGIN_LON, ORIGIN_LAT)
    half = side_m / 2
    ring = [
        (x0, y0),
        (x0 + side_m, y0),
        (x0 + side_m, y0 + half),
        (x0 + half, y0 + half),
        (x0 + half, y0 + side_m),
        (x0, y0 + side_m),
    ]
    return mapping(transform(to_wgs84, Polygon(ring)))


def _bowtie_4326(size_m: float) -> dict:
    """A real self-intersecting ("bowtie") quadrilateral — same defect
    GEO-07's validate_boundary() hard-rejects on, constructed here to
    feed geometry_confidence() directly (bypassing that hard reject) so
    the function's OWN internal validity handling is under test, not
    just its callers' upstream discipline."""
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{UTM44N}", always_xy=True).transform
    to_wgs84 = Transformer.from_crs(f"EPSG:{UTM44N}", "EPSG:4326", always_xy=True).transform
    x0, y0 = to_utm(ORIGIN_LON, ORIGIN_LAT)
    ring = [(x0, y0), (x0 + size_m, y0 + size_m), (x0, y0 + size_m), (x0 + size_m, y0), (x0, y0)]
    return mapping(transform(to_wgs84, Polygon(ring)))


def test_thresholds_are_pack_sourced_not_hard_coded(monkeypatch):
    """A boundary that would pass the real pack's plausibility envelope
    must be rejectable purely by overriding the config pack — proves
    validate_boundary() reads the threshold at call time rather than
    from a module-level constant."""
    boundary = _square_4326(50.0)  # ~2500 m^2, well inside the real pack's envelope
    validate_boundary(boundary)  # sanity: passes under the real pack

    monkeypatch.setattr(
        "solarfit.packs.config_pack.get_max_plausible_boundary_area_m2", lambda **kw: 100.0
    )
    with pytest.raises(GeometryRejected, match="implausibly large"):
        validate_boundary(boundary)


def test_max_centroid_distance_is_pack_sourced(monkeypatch):
    boundary = _square_4326(20.0)
    far_centroid = {"type": "Point", "coordinates": [ORIGIN_LON + 0.01, ORIGIN_LAT]}  # ~1 km away

    with pytest.raises(GeometryRejected, match="site centroid"):
        validate_boundary(boundary, centroid=far_centroid)  # rejected under the real (500 m) default

    monkeypatch.setattr("solarfit.packs.config_pack.get_max_centroid_distance_m", lambda **kw: 2000.0)
    validate_boundary(boundary, centroid=far_centroid)  # now passes — override raised the limit


def test_area_near_the_implausibility_bound_lowers_confidence():
    """GEO-09: area plausibility as a graded signal, not just
    validate_boundary's hard reject."""
    typical = _square_4326(200.0)  # 40,000 m^2 — comfortably mid-envelope
    borderline_small = _square_4326(2.5)  # 6.25 m^2 — within 2x of the 5 m^2 floor

    now = datetime(2026, 8, 25, tzinfo=UTC)
    score_typical = geometry_confidence(source="manual_polygon", boundary=typical, now=now)
    score_borderline = geometry_confidence(source="manual_polygon", boundary=borderline_small, now=now)

    assert score_borderline < score_typical


# ---------------------------------------------------------------------------
# GEO-09 review: vertex count removed as a confidence signal, replaced by
# actual geometry validity. Case numbers below match the fix's own testing
# requirements list.
# ---------------------------------------------------------------------------


def test_case1_valid_four_point_rectangle_gets_no_vertex_penalty():
    """Case 1. A real, valid 4-point rectangular roof — the exact
    scenario the old vertex-count penalty misfired on. Base
    manual_polygon (0.75) minus only the applicable 1-3-year imagery
    penalty (-0.05) = 0.70, NOT 0.60 (the old -0.10 vertex penalty must
    not apply)."""
    rectangle = _square_4326(20.0)  # a plausible, comfortably-mid-envelope roof
    now = datetime(2026, 1, 1, tzinfo=UTC)
    imagery_date = datetime(2024, 8, 1, tzinfo=UTC)  # ~1.4 years old -> -0.05 band

    confidence = geometry_confidence(
        source="manual_polygon", imagery_date=imagery_date, boundary=rectangle, now=now
    )

    assert confidence == pytest.approx(0.70, abs=0.001)


def test_case2_valid_multi_point_polygon_is_not_penalized_either():
    """Case 2. A real, valid multi-point (6-vertex L-shape) boundary —
    same base/imagery treatment as the 4-point rectangle above, no extra
    credit or debit for having more corners."""
    l_shape = _l_shape_4326(20.0)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    imagery_date = datetime(2024, 8, 1, tzinfo=UTC)  # ~1.4 years old -> -0.05 band

    confidence = geometry_confidence(
        source="manual_polygon", imagery_date=imagery_date, boundary=l_shape, now=now
    )

    assert confidence == pytest.approx(0.70, abs=0.001)


def test_case3_self_intersecting_polygon_lowers_confidence():
    """Case 3. A genuinely invalid (self-intersecting) polygon IS a real
    quality problem, and must still cost confidence — geometry_
    confidence() checks this itself rather than assuming every caller
    already ran validate_boundary()'s hard reject first."""
    valid = _square_4326(20.0)
    bowtie = _bowtie_4326(20.0)
    now = datetime(2026, 1, 1, tzinfo=UTC)  # same-day imagery on both — isolates validity alone

    score_valid = geometry_confidence(source="manual_polygon", boundary=valid, now=now)
    score_bowtie = geometry_confidence(source="manual_polygon", boundary=bowtie, now=now)

    assert score_bowtie < score_valid
    assert score_bowtie == pytest.approx(score_valid - 0.10, abs=0.001)


def test_case3_unparseable_boundary_also_lowers_confidence():
    """Case 3, continued: not-a-polygon and malformed input hit the same
    validity penalty as a self-intersecting one — any geometry that
    can't actually be measured is exactly as untrustworthy."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    score_missing_type = geometry_confidence(
        source="manual_polygon", boundary={"coordinates": [[[0, 0]]]}, now=now
    )
    score_point_not_polygon = geometry_confidence(
        source="manual_polygon",
        boundary={"type": "Point", "coordinates": [ORIGIN_LON, ORIGIN_LAT]},
        now=now,
    )
    baseline = geometry_confidence(source="manual_polygon", boundary=None, now=now)

    assert score_missing_type < baseline
    assert score_point_not_polygon < baseline


def test_case6_old_imagery_still_lowers_confidence():
    """Case 6. The existing imagery-age logic is untouched by this
    change — still degrades confidence for old imagery, on a valid
    boundary, independent of vertex count."""
    boundary = _square_4326(20.0)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    fresh = geometry_confidence(
        source="manual_polygon", imagery_date=now, boundary=boundary, now=now
    )
    ancient = geometry_confidence(
        source="manual_polygon",
        imagery_date=datetime(2018, 1, 1, tzinfo=UTC),  # >5 years old -> -0.20 band
        boundary=boundary,
        now=now,
    )

    assert ancient < fresh
    assert fresh == pytest.approx(0.75, abs=0.001)  # base manual_polygon, no penalties at all
    assert ancient == pytest.approx(0.55, abs=0.001)  # 0.75 - 0.20


def test_case7_vertex_count_alone_does_not_move_confidence():
    """Case 7. The core regression guard: a 4-vertex square, a 6-vertex
    L-shape, and an 8-vertex octagon — all valid, all comfortably inside
    the plausible-area envelope, same source, same imagery — must score
    IDENTICALLY. Only geometry validity and area plausibility may move
    this number now, never raw point count."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    imagery_date = datetime(2025, 6, 1, tzinfo=UTC)

    four_vertex = geometry_confidence(
        source="manual_polygon", imagery_date=imagery_date, boundary=_square_4326(20.0), now=now
    )
    six_vertex = geometry_confidence(
        source="manual_polygon", imagery_date=imagery_date, boundary=_l_shape_4326(20.0), now=now
    )
    eight_vertex = geometry_confidence(
        source="manual_polygon", imagery_date=imagery_date, boundary=_octagon_4326(20.0), now=now
    )

    assert four_vertex == six_vertex == eight_vertex
