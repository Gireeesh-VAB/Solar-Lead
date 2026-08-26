"""STUB — Owner: Person 1 (Site & Geometry).

Implements GEO-02 (MANUAL_POLYGON) of
Solar_Fitness_Engine_Development_Document_v1.1: operator draws boundary
+ exclusions on satellite imagery, edits vertices after closure, emits
GeoJSON.

Depends on: solarfit.providers.base.GeometryProvider (this person's own
protocol, same track).
"""

from solarfit.domain.site import Site


def resolve_manual(site: Site, params: dict) -> dict:
    """GEO-02. Raises NotImplementedError until Person 1 implements it."""
    raise NotImplementedError
