"""§9.2 Geometry Providers — GEO-07/GEO-09 (providers/validation.py).

No dedicated test file existed for this module before a spec-compliance
audit found two gaps here: GEO-07's plausibility/distance thresholds
were hard-coded Python constants rather than pack-sourced (CFG-01), and
GEO-09's confidence scoring never factored in area plausibility as a
graded input, only as validate_boundary's binary reject.
"""

from datetime import UTC, datetime

import pytest
from pyproj import Transformer
from shapely.geometry import box as shapely_box
from shapely.geometry import mapping
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
