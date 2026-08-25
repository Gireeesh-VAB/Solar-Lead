"""STUB — Owner: Person 2 (Rules Engine).

Implements §9.6 Generation (GEN-01..06) AND the derate half of §9.17
Shading Analysis (SHADE-03) of
Solar_Fitness_Engine_Development_Document_v1.2:

  GEN-01  Fast estimate: capacity x specific yield x performance ratio.
  GEN-02  Specific yield by district/grid-cell, refined by
          solarfit.providers.weather — never a single constant.
  GEN-03  Configurable site-type performance adjustment.
  GEN-04  (Should) Detailed estimate: plane-of-array irradiance,
          temperature, inverter losses from the Weather API.
  GEN-05  Record the estimation method on every result.
  GEN-06  (Should) P50/P90 figures for portfolio aggregation.
  SHADE-03  Multiply GEN-01's performance ratio by
            (1 - site.shading.shading_score * shading_derate_factor)
            when site.shading.source == "solar_api" — read
            shading_derate_factor via
            solarfit.packs.config_pack.get_shading_derate_factor().
            When shading is unavailable, apply no derate and note that
            in the GEN-05 method record (never silently assume
            unshaded).

Depends on: solarfit.domain.site.Site (frozen, Day 0, now carries
.shading — see domain/site.py's ShadingEstimate),
solarfit.providers.weather (this person's own client, same track),
solarfit.packs.config_pack (frozen loader, Day 0).
"""

from solarfit.domain.site import Site


def estimate_generation_kwh(site: Site, capacity_kwp: float, params: dict | None = None) -> dict:
    """GEN-01..06. Raises NotImplementedError until Person 2 implements it."""
    raise NotImplementedError
