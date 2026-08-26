"""§16 Testing — 'Projection' row: round-trip 4326 -> 32644 -> 4326
preserves coordinates; buffer of 0.5 m on a 100 m square yields
approximately 9,801 m^2.

Guards the §14/§17 non-negotiable: area/buffer math must use a
geography cast or a projected CRS — NEVER planar operations on
EPSG:4326 directly.
"""

from pyproj import Transformer
from shapely.geometry import Point, box
from shapely.ops import transform

WGS84 = "EPSG:4326"
UTM44N = "EPSG:32644"  # covers 78-84 deg E, most of Andhra Pradesh — see §14


def test_roundtrip_preserves_coordinates():
    to_utm = Transformer.from_crs(WGS84, UTM44N, always_xy=True)
    to_wgs84 = Transformer.from_crs(UTM44N, WGS84, always_xy=True)

    lng, lat = 78.4867, 17.3850  # Hyderabad, well within UTM 44N coverage
    x, y = to_utm.transform(lng, lat)
    lng2, lat2 = to_wgs84.transform(x, y)

    assert abs(lng2 - lng) < 1e-9
    assert abs(lat2 - lat) < 1e-9


def test_negative_buffer_on_100m_square():
    # Build the square directly in the projected CRS — this is the
    # pattern engine/area.py must follow: transform to a projected CRS
    # *before* buffering, never buffer coordinates that are still in
    # degrees (EPSG:4326).
    square = box(0, 0, 100, 100)
    setback = square.buffer(-0.5)  # AREA-03's edge setback, metres

    assert abs(setback.area - 9_801.0) < 1e-6


def test_point_transform_via_shapely_ops():
    to_utm = Transformer.from_crs(WGS84, UTM44N, always_xy=True)
    pt = Point(78.4867, 17.3850)
    projected = transform(to_utm.transform, pt)

    # Sanity bounds for UTM 44N easting/northing near Hyderabad —
    # confirms the transform actually ran, not just returned the input.
    assert 200_000 < projected.x < 800_000
    assert 1_000_000 < projected.y < 3_000_000
