"""STUB — Owner: Person 1 (Site & Geometry).

Implements §9.3 Usable Area (AREA-01..06) of
Solar_Fitness_Engine_Development_Document_v1.1:

  AREA-01  Boundary area via geography cast or projected CRS.
           NEVER planar area on EPSG:4326 (see §14 PostGIS Rules, §17).
  AREA-02  Total exclusion area — overlapping exclusions unioned, not summed.
  AREA-03  Configurable edge setback as a negative buffer in a projected CRS.
           Read edge_setback_m from solarfit.packs.config_pack.get_edge_setback_m().
  AREA-04  usable_area = boundary - setback - exclusions - type deductions.
  AREA-05  Utilisation factor by class where per-site precision is
           unavailable. Read via
           solarfit.packs.config_pack.get_utilisation_factor(site_type).
  AREA-06  Return zero, never negative, when setback consumes the boundary.

Depends on: solarfit.domain.site.Site (frozen, Day 0),
solarfit.packs.config_pack (frozen loader, Day 0).
"""

from solarfit.domain.site import Site


def compute_usable_area_m2(site: Site, params: dict | None = None) -> float:
    """AREA-01..06. Raises NotImplementedError until Person 1 implements it."""
    raise NotImplementedError
