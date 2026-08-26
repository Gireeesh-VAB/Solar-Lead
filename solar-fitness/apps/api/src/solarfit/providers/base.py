"""STUB — Owner: Person 1 (Site & Geometry).

Implements GEO-01 of Solar_Fitness_Engine_Development_Document_v1.1: a
GeometryProvider protocol plus a provider-precedence registry that
resolves the applicable provider chain at runtime.

Providers registered here (rooftop-only scope — GEO-03 WATER_INDEX is
on hold, deliberately absent):
  - manual.py       MANUAL_POLYGON  (GEO-02)
  - solar_api.py    SOLAR_API       (GEO-04)
  - imported.py     IMPORTED        (GEO-05)
  - FIELD_MEASURED  (GEO-06) — supersedes any remote geometry; likely
    lives in repositories/sites.py alongside SITE-05 versioning rather
    than as a separate provider module. Your call.

Also owns, in this module or a sibling validation.py:
  GEO-07  Reject self-intersecting geometry, <3 vertices, out-of-range
          distance from centroid, implausible area for the site type.
  GEO-08  Reject an exclusion polygon not contained within its boundary.
  GEO-09  Geometry confidence from source, imagery recency, vertex
          count, area plausibility.

Depends on: solarfit.domain.site.Site (frozen, Day 0).
"""

from typing import Protocol

from solarfit.domain.site import Site


class GeometryProvider(Protocol):
    id: str
    applies_to: list[str]  # site types

    def resolve(self, site: Site, params: dict) -> dict: ...  # returns a GeoJSON Boundary
