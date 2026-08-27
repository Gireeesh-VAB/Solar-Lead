"""§9.3 Usable Area (AREA-01..06) — Person 1.

Fixtures are built in EPSG:4326 (degrees), the way a real Site carries
them, so these tests exercise the projection step rather than assuming it
away. Expected values are hand-computed from the projected square, with a
tolerance that absorbs the small distortion of projecting a lat/lng box
into UTM.
"""

from datetime import UTC, datetime

import pytest
from pyproj import Transformer
from shapely.geometry import box as shapely_box
from shapely.geometry import mapping, shape
from shapely.ops import transform

from solarfit.domain.site import Site
from solarfit.engine.area import boundary_area_m2, compute_usable_area_m2, exclusion_area_m2
from solarfit.engine.projection import to_metric, utm_epsg_for

# Hyderabad — inside UTM 44N (EPSG:32644), the zone tests/test_projection.py pins.
ORIGIN_LON, ORIGIN_LAT = 78.4867, 17.3850
UTM44N = 32644


def _square_4326(side_m: float, *, offset_m: tuple[float, float] = (0.0, 0.0)) -> dict:
    """A `side_m` x `side_m` square near Hyderabad, as GeoJSON in EPSG:4326.

    Built in UTM and projected back out, so the metre dimensions are exact
    at construction and the code under test has to undo the projection
    itself.
    """
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{UTM44N}", always_xy=True).transform
    to_wgs84 = Transformer.from_crs(f"EPSG:{UTM44N}", "EPSG:4326", always_xy=True).transform

    x0, y0 = to_utm(ORIGIN_LON, ORIGIN_LAT)
    dx, dy = offset_m
    square = shapely_box(x0 + dx, y0 + dy, x0 + dx + side_m, y0 + dy + side_m)
    return mapping(transform(to_wgs84, square))


def _site(boundary: dict | None, exclusions: dict | None = None, **kwargs) -> Site:
    return Site(
        id=kwargs.get("id", "site-test"),
        site_type=kwargs.get("site_type", "ROOFTOP_RESIDENTIAL"),
        name="Test roof",
        owner_org="org-test",
        jurisdiction="IN-TG",
        centroid={"type": "Point", "coordinates": [ORIGIN_LON, ORIGIN_LAT]},
        boundary=boundary,
        exclusions=exclusions,
        created_at=datetime(2026, 8, 25, tzinfo=UTC),
    )


# --------------------------------------------------------------------- #
# projection
# --------------------------------------------------------------------- #


def test_utm_zone_derived_from_longitude_not_hardcoded():
    assert utm_epsg_for(ORIGIN_LON, ORIGIN_LAT) == UTM44N  # Hyderabad, 44N
    assert utm_epsg_for(72.8777, 19.0760) == 32643  # Mumbai, 43N
    assert utm_epsg_for(-43.1729, -22.9068) == 32723  # Rio, 23S


def test_to_metric_reuses_a_supplied_zone():
    geom, epsg = to_metric(shape(_square_4326(10)), epsg=UTM44N)
    assert epsg == UTM44N
    assert not geom.is_empty


# --------------------------------------------------------------------- #
# AREA-01 — boundary area, never planar 4326
# --------------------------------------------------------------------- #


def test_boundary_area_of_a_100m_square_is_10000_m2():
    site = _site(_square_4326(100))
    assert boundary_area_m2(site) == pytest.approx(10_000.0, rel=1e-3)


def test_area_is_not_planar_degrees():
    """The §17 non-negotiable, stated as a test.

    Planar area on the raw 4326 coordinates of a 100 m square is ~8e-7
    square degrees. Anything in that neighbourhood means the projection
    step was skipped.
    """
    site = _site(_square_4326(100))
    planar = shape(site.boundary).area
    assert planar < 1e-5  # confirms the fixture really is in degrees
    assert boundary_area_m2(site) > 9_000.0


# --------------------------------------------------------------------- #
# AREA-03 — setback as a negative buffer
# --------------------------------------------------------------------- #


def test_setback_shrinks_the_measured_area():
    site = _site(_square_4326(100))
    # 0.5 m setback on a 100 m square -> 99 x 99 = 9,801 m^2, matching
    # tests/test_projection.py's expectation, then x utilisation.
    usable = compute_usable_area_m2(
        site, {"edge_setback_m": 0.5, "utilisation_factor": 1.0}
    )
    assert usable == pytest.approx(9_801.0, rel=1e-3)


def test_zero_setback_leaves_the_boundary_intact():
    site = _site(_square_4326(100))
    usable = compute_usable_area_m2(site, {"edge_setback_m": 0, "utilisation_factor": 1.0})
    assert usable == pytest.approx(10_000.0, rel=1e-3)


def test_negative_setback_is_rejected():
    site = _site(_square_4326(100))
    with pytest.raises(ValueError, match="must not be negative"):
        compute_usable_area_m2(site, {"edge_setback_m": -1.0})


# --------------------------------------------------------------------- #
# AREA-02 — exclusions unioned, not summed
# --------------------------------------------------------------------- #


def test_single_exclusion_is_deducted():
    boundary = _square_4326(100)
    exclusion = _square_4326(10, offset_m=(20.0, 20.0))  # 100 m^2, well inside
    site = _site(boundary, {"type": "MultiPolygon", "coordinates": [exclusion["coordinates"]]})

    assert exclusion_area_m2(site) == pytest.approx(100.0, rel=1e-2)
    usable = compute_usable_area_m2(site, {"edge_setback_m": 0, "utilisation_factor": 1.0})
    assert usable == pytest.approx(9_900.0, rel=1e-3)


def test_overlapping_exclusions_are_unioned_not_summed():
    """AREA-02's whole point: two 10x10 obstacles overlapping by 5x5 must
    deduct 175 m^2, not 200 m^2."""
    boundary = _square_4326(100)
    a = _square_4326(10, offset_m=(20.0, 20.0))
    b = _square_4326(10, offset_m=(25.0, 25.0))  # overlaps `a` on a 5x5 corner
    site = _site(
        boundary,
        {"type": "MultiPolygon", "coordinates": [a["coordinates"], b["coordinates"]]},
    )

    assert exclusion_area_m2(site) == pytest.approx(175.0, rel=1e-2)

    usable = compute_usable_area_m2(site, {"edge_setback_m": 0, "utilisation_factor": 1.0})
    assert usable == pytest.approx(10_000.0 - 175.0, rel=1e-3)


def test_no_exclusions_deducts_nothing():
    site = _site(_square_4326(100))
    assert exclusion_area_m2(site) == 0.0


# --------------------------------------------------------------------- #
# AREA-04 — ordering: setback first, then exclusions
# --------------------------------------------------------------------- #


def test_edge_exclusion_is_not_double_counted_with_the_setback():
    """An exclusion straddling the roof edge overlaps the setback ring.

    Applying the setback first and subtracting exclusions from the result
    counts that overlap once. Summing the two deductions independently
    would count it twice and under-report usable area.
    """
    boundary = _square_4326(100)
    # 10x10 obstacle hanging off the left edge: half in, half out.
    edge = _square_4326(10, offset_m=(-5.0, 40.0))
    site = _site(boundary, {"type": "MultiPolygon", "coordinates": [edge["coordinates"]]})

    usable = compute_usable_area_m2(
        site, {"edge_setback_m": 1.0, "utilisation_factor": 1.0}
    )

    # setback ring leaves 98x98 = 9,604. The obstacle's remaining overlap
    # with that inner square is 4 m wide x 10 m tall = 40 m^2.
    assert usable == pytest.approx(9_604.0 - 40.0, rel=1e-3)


# --------------------------------------------------------------------- #
# AREA-05 — utilisation factor
# --------------------------------------------------------------------- #


def test_utilisation_factor_scales_the_result():
    site = _site(_square_4326(100))
    usable = compute_usable_area_m2(site, {"edge_setback_m": 0, "utilisation_factor": 0.70})
    assert usable == pytest.approx(7_000.0, rel=1e-3)


def test_utilisation_factor_defaults_to_the_config_pack():
    """AREA-05 reads the by-class factor from Person 2's pack rather than
    hard-coding one (CFG-01). rooftop_v1.yaml currently has 0.70 for
    ROOFTOP_RESIDENTIAL; assert the wiring, not the placeholder value."""
    from solarfit.packs import config_pack

    site = _site(_square_4326(100))
    expected = 10_000.0 * config_pack.get_utilisation_factor("ROOFTOP_RESIDENTIAL")
    usable = compute_usable_area_m2(site, {"edge_setback_m": 0})
    assert usable == pytest.approx(expected, rel=1e-3)


def test_unknown_site_type_raises_rather_than_defaulting():
    """config_pack must not substitute a made-up number for a site type
    it has no entry for."""
    site = _site(_square_4326(100))
    object.__setattr__(site, "site_type", "ROOFTOP_UNKNOWN")
    with pytest.raises(KeyError):
        compute_usable_area_m2(site, {"edge_setback_m": 0})


# --------------------------------------------------------------------- #
# AREA-06 — clamp at zero, never negative
# --------------------------------------------------------------------- #


def test_setback_wider_than_the_roof_returns_zero_not_negative():
    site = _site(_square_4326(4))  # 4 m square
    usable = compute_usable_area_m2(site, {"edge_setback_m": 5.0, "utilisation_factor": 1.0})
    assert usable == 0.0


def test_exclusions_covering_the_whole_roof_return_zero():
    boundary = _square_4326(20)
    covering = _square_4326(40, offset_m=(-10.0, -10.0))  # swallows the boundary
    site = _site(boundary, {"type": "MultiPolygon", "coordinates": [covering["coordinates"]]})

    usable = compute_usable_area_m2(site, {"edge_setback_m": 0, "utilisation_factor": 1.0})
    assert usable == 0.0


# --------------------------------------------------------------------- #
# missing geometry is INSUFFICIENT_DATA, not zero
# --------------------------------------------------------------------- #


def test_missing_boundary_raises_rather_than_returning_zero():
    """A site with no resolved boundary is a different condition from a
    roof with no usable area. Returning 0.0 here would let a geometry
    failure masquerade as a real 'this roof is unusable' verdict."""
    site = _site(None)
    with pytest.raises(ValueError, match="no boundary"):
        compute_usable_area_m2(site)
