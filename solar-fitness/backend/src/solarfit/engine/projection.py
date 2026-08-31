"""Owner: Person 1 (Site & Geometry).

Shared projection helper behind §14's PostGIS Rules and §17's first
non-negotiable: area, buffer and distance are metric operations and must
run in a projected CRS. EPSG:4326 coordinates are DEGREES — an "area"
computed on them is not an area, it is a number that happens to look
plausible, which is exactly why the bug survives to production.

Used by engine/area.py (AREA-01/03) and by the GEO-07 validation checks
(distance-from-centroid, area plausibility), so it lives in one place
rather than being re-derived per call site.

Zone selection is derived from the geometry's own centroid, never
hard-coded. tests/test_projection.py pins EPSG:32644 because it covers
Hyderabad (78-84 deg E) — but a site outside that longitude band needs a
different zone, and a hard-coded 32644 would silently return wrong
areas for it.
"""

from pyproj import Transformer
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

WGS84_EPSG = 4326

__all__ = ["WGS84_EPSG", "to_metric", "utm_epsg_for"]


def utm_epsg_for(lon: float, lat: float) -> int:
    """EPSG code of the WGS84 UTM zone containing (lon, lat).

    32601..32660 north of the equator, 32701..32760 south.

        >>> utm_epsg_for(78.4867, 17.3850)  # Hyderabad
        32644
    """
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"longitude out of range: {lon}")
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"latitude out of range: {lat}")

    zone = int((lon + 180.0) // 6.0) + 1
    zone = min(zone, 60)  # lon == 180.0 exactly would otherwise give 61
    return (32600 if lat >= 0 else 32700) + zone


def to_metric(geom: BaseGeometry, *, epsg: int | None = None) -> tuple[BaseGeometry, int]:
    """Project an EPSG:4326 geometry into a metric CRS.

    Returns the projected geometry and the EPSG code used. Pass that code
    back in as `epsg` for any related geometry — a boundary and its
    exclusions must be measured in the SAME projection, so the zone is
    chosen once from the boundary and reused, not re-derived per part.
    """
    if geom.is_empty:
        raise ValueError("cannot project an empty geometry")

    if epsg is None:
        centroid = geom.centroid
        epsg = utm_epsg_for(centroid.x, centroid.y)

    to_projected = Transformer.from_crs(
        f"EPSG:{WGS84_EPSG}", f"EPSG:{epsg}", always_xy=True
    ).transform
    return transform(to_projected, geom), epsg
