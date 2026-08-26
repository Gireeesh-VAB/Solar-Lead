"""STUB — Owner: Person 1 (Site & Geometry).

Implements GEO-05 (IMPORTED) of
Solar_Fitness_Engine_Development_Document_v1.1: GeoJSON/shapefile
upload with CRS detection and validation. Backs routers/imports.py's
bulk-import endpoint (API-07).

Depends on: solarfit.providers.base (same track).
"""

from solarfit.domain.site import Site


def resolve_imported(site: Site, upload: bytes, params: dict) -> dict:
    """GEO-05. Raises NotImplementedError until Person 1 implements it."""
    raise NotImplementedError
