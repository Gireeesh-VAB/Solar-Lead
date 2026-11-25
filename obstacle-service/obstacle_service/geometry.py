"""Geometry helpers: pixels -> lng/lat, on-roof test, clipping to the roof, plausibility checks. Pure functions, no models, no network."""
from __future__ import annotations

from pyproj import Geod, Transformer
from shapely.geometry import Polygon, mapping, shape

from obstacle_service.satellite_frame import Frame

_GEOD = Geod(ellps="WGS84")


def pixel_polygon_to_geojson(poly: Polygon, frame: Frame) -> dict | None:
    """Pixel-space outline -> GeoJSON Polygon in EPSG:4326, through the frame's own affine transform."""
    poly = poly.simplify(1.0, preserve_topology=True)
    if poly.is_empty or poly.geom_type != "Polygon":
        return None
    native = [frame.transform * (col, row) for col, row in poly.exterior.coords]
    if frame.epsg != 4326:
        to_wgs84 = Transformer.from_crs(f"EPSG:{frame.epsg}", "EPSG:4326", always_xy=True)
        native = [to_wgs84.transform(x, y) for x, y in native]
    ring = [list(pt) for pt in native]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def mostly_on_roof(geojson: dict, roof, minimum: float) -> bool:
    """True when at least `minimum` of the outline's area lies on the roof. Geometry trouble counts as "keep" (the clip and validation decide)."""
    try:
        outline = shape(geojson).buffer(0)
        if outline.is_empty or outline.area <= 0:
            return False
        return outline.intersection(roof).area / outline.area >= minimum
    except Exception:  # noqa: BLE001
        return True


def clip_polygon_to_boundary(geojson: dict, boundary_geom) -> dict | None:
    """Clip an obstacle's polygon to the roof. Detector masks are pixel-based, so along the roof edge they can poke past it; clipping keeps the
    part on the roof. Returns None when nothing is left, and the input unchanged when there is no usable boundary or on a geometry error."""
    if boundary_geom is None or boundary_geom.is_empty:
        return geojson
    try:
        # Clip to the boundary inset by ~1 cm: an exact intersection leaves vertices a hair outside after float rounding, and the strict
        # `covers` check in validate_obstacle() would then reject the polygon we just clipped to fit.
        inner = boundary_geom.buffer(-1e-7)
        target = inner if not inner.is_empty else boundary_geom
        clipped = shape(geojson).buffer(0).intersection(target)
    except Exception:  # noqa: BLE001
        return geojson
    if clipped.is_empty:
        return None
    if clipped.geom_type != "Polygon":
        polygons = [g for g in getattr(clipped, "geoms", []) if g.geom_type == "Polygon" and not g.is_empty]
        if not polygons:
            return None
        clipped = max(polygons, key=lambda g: g.area)
    return mapping(clipped)


def geodesic_area_m2(geom) -> float:
    """Area in m2 of a lng/lat polygon (ellipsoidal, not planar degrees)."""
    area, _ = _GEOD.geometry_area_perimeter(geom)
    return abs(area)


def is_plausible_obstacle(geojson: dict, boundary: dict, *, min_area_m2: float, max_fraction: float) -> bool:
    """Valid geometry, fully inside the roof, not noise-small, not implausibly large for the roof it is on."""
    try:
        poly = shape(geojson)
        roof = shape(boundary)
    except Exception:  # noqa: BLE001 - shapely raises its own GeometryTypeError for unknown types; malformed input is "not plausible", never a crash
        return False
    if poly.is_empty or not poly.is_valid or poly.geom_type != "Polygon" or len(set(poly.exterior.coords)) < 3:
        return False
    if not roof.is_valid:
        roof = roof.buffer(0)
    if not roof.covers(poly):
        return False
    area = geodesic_area_m2(poly)
    roof_area = geodesic_area_m2(roof) if roof.geom_type == "Polygon" else 0.0
    if area < min_area_m2:
        return False
    return not (roof_area > 0 and area / roof_area > max_fraction)
