"""§16 Testing — AREA-01..06 keeping the polygon, not just the number.

The chain in compute_usable_roof() has always built the usable shape:
boundary, minus the edge setback, minus the unioned exclusions. It then
threw it away and returned a float. Handed only a float, a panel-layout
algorithm can do nothing but assume a rectangle — which is how panels end
up beside a building instead of on it.

The assertion that matters most is the last group: the polygon must be
the shape AFTER setback and exclusions, in the right place on the earth,
and the area value must not have moved by a single square metre.
"""

import math
from datetime import UTC, datetime

import pytest
from pyproj import Transformer
from shapely.geometry import mapping, shape

from solarfit.domain.site import Site
from solarfit.engine.area import compute_usable_area_m2, compute_usable_roof
from solarfit.engine.projection import to_metric

ORIGIN_LNG, ORIGIN_LAT = 78.4867, 17.3850
PARAMS = {"edge_setback_m": 0.5, "utilisation_factor": 0.7}


def _square_4326(side_m: float, *, offset_m: tuple[float, float] = (0.0, 0.0)) -> dict:
    """A real metre-sized square, built in UTM and returned as WGS84."""
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True).transform
    to_wgs = Transformer.from_crs("EPSG:32644", "EPSG:4326", always_xy=True).transform
    x0, y0 = to_utm(ORIGIN_LNG, ORIGIN_LAT)
    x0, y0 = x0 + offset_m[0], y0 + offset_m[1]
    corners = [(x0, y0), (x0 + side_m, y0), (x0 + side_m, y0 + side_m), (x0, y0 + side_m), (x0, y0)]
    return mapping(shape({"type": "Polygon", "coordinates": [[to_wgs(x, y) for x, y in corners]]}))


def _site(boundary: dict, exclusions: dict | None = None) -> Site:
    return Site(
        id="s-1",
        site_type="ROOFTOP_RESIDENTIAL",
        name="t",
        owner_org="o",
        jurisdiction="TG",
        centroid={"type": "Point", "coordinates": [ORIGIN_LNG, ORIGIN_LAT]},
        boundary=boundary,
        exclusions=exclusions,
        created_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Backward compatibility — the number must not move
# ---------------------------------------------------------------------------


def test_the_area_value_is_unchanged():
    """Every existing caller reads this float. It must be identical."""
    site = _site(_square_4326(20.0))

    assert compute_usable_area_m2(site, PARAMS) == pytest.approx(
        compute_usable_roof(site, PARAMS).area_m2
    )


def test_the_number_still_matches_the_documented_chain():
    """20 m square, 0.5 m setback -> 19 x 19, times 0.7 utilisation."""
    site = _site(_square_4326(20.0))

    expected = (19.0 * 19.0) * 0.7
    assert compute_usable_area_m2(site, PARAMS) == pytest.approx(expected, rel=1e-3)


# ---------------------------------------------------------------------------
# The polygon itself
# ---------------------------------------------------------------------------


def test_the_polygon_is_the_shape_after_the_setback():
    """Not the raw boundary — the setback has to be visible in the shape,
    or a packer would lay panels over the roof edge."""
    roof = compute_usable_roof(_site(_square_4326(20.0)), PARAMS)

    assert roof.polygon is not None
    metric, _ = to_metric(shape(roof.polygon))
    assert math.sqrt(metric.area) == pytest.approx(19.0, rel=1e-3)


def test_the_polygon_has_the_exclusion_cut_out_of_it():
    """A water tank must be a hole in the shape, not just a smaller
    number — a packer works from the geometry."""
    boundary = _square_4326(20.0)
    exclusion = _square_4326(4.0, offset_m=(6.0, 6.0))

    with_hole = compute_usable_roof(_site(boundary, exclusion), PARAMS)
    without = compute_usable_roof(_site(boundary), PARAMS)

    hole_metric, _ = to_metric(shape(with_hole.polygon))
    plain_metric, _ = to_metric(shape(without.polygon))
    # 4 x 4 m removed from the geometry itself.
    assert plain_metric.area - hole_metric.area == pytest.approx(16.0, rel=0.05)
    assert with_hole.area_m2 < without.area_m2


def test_the_polygon_is_wgs84_and_lands_on_the_real_site():
    """GeoJSON in degrees, like every other geometry crossing this
    codebase — so it serialises to the API and draws on a map."""
    roof = compute_usable_roof(_site(_square_4326(20.0)), PARAMS)
    poly = shape(roof.polygon)

    assert roof.polygon["type"] in {"Polygon", "MultiPolygon"}
    assert poly.centroid.x == pytest.approx(ORIGIN_LNG, abs=1e-3)
    assert poly.centroid.y == pytest.approx(ORIGIN_LAT, abs=1e-3)


def test_the_metric_polygon_is_kept_for_measuring_and_packing():
    """§17: anything that measures or packs works in metres. Handing back
    only degrees would force every consumer to re-project, which is
    exactly where planar-4326 bugs get reintroduced."""
    roof = compute_usable_roof(_site(_square_4326(20.0)), PARAMS)

    assert roof.polygon_metric is not None
    assert roof.epsg == 32644  # Hyderabad's UTM zone, derived not hardcoded
    assert roof.polygon_metric.area == pytest.approx(19.0 * 19.0, rel=1e-3)


def test_the_polygon_is_the_pre_utilisation_shape():
    """A trap worth pinning: utilisation is a statistical stand-in for
    the very spacing a real packer places explicitly. The polygon is the
    shape BEFORE it, so a packer must not apply it a second time."""
    roof = compute_usable_roof(_site(_square_4326(20.0)), PARAMS)

    assert roof.polygon_metric.area == pytest.approx(19.0 * 19.0, rel=1e-3)
    assert roof.area_m2 == pytest.approx(19.0 * 19.0 * 0.7, rel=1e-3)
    assert roof.area_m2 < roof.polygon_metric.area


# ---------------------------------------------------------------------------
# AREA-06 — consumed roof, versus no roof at all
# ---------------------------------------------------------------------------


def test_a_setback_that_consumes_the_roof_gives_zero_and_no_polygon():
    """Zero usable area is a real answer, and there is genuinely no shape
    to hand a packer."""
    roof = compute_usable_roof(_site(_square_4326(2.0)), {"edge_setback_m": 5.0})

    assert roof.area_m2 == 0.0
    assert roof.polygon is None
    assert roof.polygon_metric is None


def test_an_exclusion_covering_the_whole_roof_gives_zero_and_no_polygon():
    boundary = _square_4326(10.0)
    roof = compute_usable_roof(_site(boundary, _square_4326(30.0, offset_m=(-10.0, -10.0))), PARAMS)

    assert roof.area_m2 == 0.0
    assert roof.polygon is None


def test_a_site_with_no_boundary_still_raises():
    """AREA-06's zero and 'we never resolved a roof' are different
    answers and must never be conflated."""
    with pytest.raises(ValueError, match="no boundary"):
        compute_usable_roof(_site(None), PARAMS)
