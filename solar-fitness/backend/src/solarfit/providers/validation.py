"""Owner: Person 1 (Site & Geometry).

GEO-07, GEO-08 and GEO-09 of
Solar_Fitness_Engine_Development_Document_v1.1 — the geometry-rejection
and confidence rules that every provider funnels through, so a bad
polygon is rejected once rather than once per provider.

  GEO-07  Reject self-intersecting geometry, <3 vertices, out-of-range
          distance from centroid, implausible area for the site type.
  GEO-08  Reject an exclusion polygon not contained within its boundary.
  GEO-09  Geometry confidence from source, imagery recency, vertex
          count, area plausibility.

Rejection is loud (GeometryRejected) rather than silent repair. A trace
the system quietly "fixed" is a number nobody can explain later — and
§17 is explicit that a wrong area must never look like a right one.
"""

from __future__ import annotations

from datetime import UTC, datetime

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

from solarfit.domain.site import GeometrySource
from solarfit.engine.projection import to_metric

__all__ = [
    "MAX_CENTROID_DISTANCE_M",
    "MAX_PLAUSIBLE_AREA_M2",
    "MIN_PLAUSIBLE_AREA_M2",
    "GeometryRejected",
    "geometry_confidence",
    "validate_boundary",
    "validate_exclusion",
]

# GEO-07 plausibility envelope. A rooftop smaller than a parking space or
# larger than a stadium is a units error or a mis-traced neighbourhood,
# not a roof. Deliberately wide — this rejects nonsense, it does not
# second-guess a genuinely large industrial roof.
MIN_PLAUSIBLE_AREA_M2 = 5.0
MAX_PLAUSIBLE_AREA_M2 = 500_000.0

# GEO-07 — a boundary this far from the site's own centroid means the
# geocode and the trace disagree about which building we are looking at.
MAX_CENTROID_DISTANCE_M = 500.0

MIN_VERTICES = 3


class GeometryRejected(ValueError):
    """GEO-07/08. The geometry is not usable and was not repaired."""


def _exterior_vertex_count(geom: BaseGeometry) -> int:
    # A closed ring repeats its first point, so the distinct count is one
    # fewer than the coordinate list.
    coords = list(geom.exterior.coords)
    return len(coords) - 1 if len(coords) > 1 and coords[0] == coords[-1] else len(coords)


def validate_boundary(boundary: dict, *, centroid: dict | None = None) -> BaseGeometry:
    """GEO-07. Return the boundary as a Shapely geometry, or raise.

    Checks, in order: parseable, is a polygon, non-empty, enough
    vertices, simple (no self-intersection), plausible area, and — when a
    centroid is supplied — close enough to it.
    """
    try:
        geom = shape(boundary)
    except Exception as exc:  # malformed GeoJSON
        raise GeometryRejected(f"boundary is not parseable GeoJSON: {exc}") from exc

    if geom.geom_type != "Polygon":
        raise GeometryRejected(f"boundary must be a Polygon, got {geom.geom_type}")

    if geom.is_empty:
        raise GeometryRejected("boundary is empty")

    vertices = _exterior_vertex_count(geom)
    if vertices < MIN_VERTICES:
        raise GeometryRejected(f"boundary has {vertices} vertices, needs at least {MIN_VERTICES}")

    # is_valid catches self-intersection ("bowtie" traces), the single
    # most common defect in a hand-drawn polygon.
    if not geom.is_valid:
        raise GeometryRejected("boundary is self-intersecting or otherwise invalid")

    metric, epsg = to_metric(geom)
    area = metric.area
    if area < MIN_PLAUSIBLE_AREA_M2:
        raise GeometryRejected(f"boundary area {area:.1f} m² is implausibly small")
    if area > MAX_PLAUSIBLE_AREA_M2:
        raise GeometryRejected(f"boundary area {area:.1f} m² is implausibly large")

    if centroid:
        centre_metric, _ = to_metric(shape(centroid), epsg=epsg)
        distance = metric.centroid.distance(centre_metric)
        if distance > MAX_CENTROID_DISTANCE_M:
            raise GeometryRejected(
                f"boundary centre is {distance:.0f} m from the site centroid "
                f"(limit {MAX_CENTROID_DISTANCE_M:.0f} m) — likely the wrong building"
            )

    return geom


def validate_exclusion(exclusion: dict, boundary: BaseGeometry) -> BaseGeometry:
    """GEO-08. An exclusion must be a valid polygon inside its boundary."""
    try:
        geom = shape(exclusion)
    except Exception as exc:
        raise GeometryRejected(f"exclusion is not parseable GeoJSON: {exc}") from exc

    if geom.geom_type != "Polygon":
        raise GeometryRejected(f"exclusion must be a Polygon, got {geom.geom_type}")
    if geom.is_empty:
        raise GeometryRejected("exclusion is empty")
    if not geom.is_valid:
        raise GeometryRejected("exclusion is self-intersecting or otherwise invalid")

    # `within` is too strict for a real trace: an obstacle drawn flush to
    # the roof edge shares a boundary segment. Require real overlap and
    # no meaningful spill instead.
    if not geom.intersects(boundary):
        raise GeometryRejected("exclusion lies entirely outside its boundary")

    outside = geom.difference(boundary)
    if not outside.is_empty and outside.area > geom.area * 0.01:
        raise GeometryRejected(
            "exclusion extends beyond its boundary — it cannot deduct area the roof never had"
        )

    return geom


def geometry_confidence(
    *,
    source: GeometrySource | None,
    imagery_date: datetime | None = None,
    boundary: dict | None = None,
    now: datetime | None = None,
) -> float:
    """GEO-09. Confidence in the stored geometry, 0..1.

    Feeds Person 4's FIT-04 directly, so it must degrade for the reasons
    a human would distrust a polygon: where it came from, how old the
    imagery is, and how much detail the trace actually carries.

    Deliberately returns a number, never None — a site always has *some*
    confidence. Absence of geometry is the caller's INSUFFICIENT_DATA
    case, not a zero here.
    """
    if source is None:
        return 0.0

    # Base rate by provenance, mirroring base.PRECEDENCE's ordering.
    base_score = {
        "field_measured": 0.95,
        "manual_polygon": 0.75,
        "imported": 0.65,
        "solar_api": 0.60,
    }.get(source, 0.3)

    score = base_score

    # Imagery recency. Field measurement is ground truth and does not
    # decay with imagery age; everything derived from a picture does.
    if source != "field_measured" and imagery_date is not None:
        now = now or datetime.now(UTC)
        if imagery_date.tzinfo is None:
            imagery_date = imagery_date.replace(tzinfo=UTC)
        years = max(0.0, (now - imagery_date).days / 365.25)
        if years > 5:
            score -= 0.20
        elif years > 3:
            score -= 0.10
        elif years > 1:
            score -= 0.05

    # Vertex count as a proxy for detail: a four-corner box over a real
    # roof is a rectangle someone drew quickly, not a traced outline.
    if boundary:
        try:
            geom = shape(boundary)
            vertices = _exterior_vertex_count(geom)
        except (ValueError, TypeError, AttributeError):
            vertices = 0
        if vertices <= 4:
            score -= 0.10
        elif vertices >= 8:
            score += 0.05

    return round(min(1.0, max(0.0, score)), 3)


def centroid_of(boundary: dict) -> dict:
    """The boundary's own centroid as GeoJSON — used when a site is
    created from geometry rather than from a geocoded address."""
    geom = shape(boundary)
    point: Point = geom.centroid
    return {"type": "Point", "coordinates": [point.x, point.y]}
