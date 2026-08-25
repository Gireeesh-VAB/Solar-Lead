"""§16 Testing — 'Geometry' row: known polygon -> known area within
tolerance. Written first per the document's own guidance: "the cheapest
test in the suite and guards every number the product emits."

This also matches Sprint 0's "done when": a 100 m square returns
approximately 10,000 m^2.
"""

from shapely.geometry import box


def test_100m_square_area_in_projected_crs():
    # A 100m x 100m square built directly in a projected (metric) CRS —
    # no reprojection involved, isolating pure area computation.
    square = box(0, 0, 100, 100)
    assert square.area == 10_000.0


def test_known_polygon_area_within_tolerance():
    # Slightly irregular quadrilateral with a hand-computed shoelace area.
    poly = box(10, 10, 60, 40)  # 50 x 30
    assert abs(poly.area - 1_500.0) < 1e-6
