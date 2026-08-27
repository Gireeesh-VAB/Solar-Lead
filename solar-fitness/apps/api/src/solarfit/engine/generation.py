"""Owner: Person 2 (Rules Engine).

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
            (1 - shaded_fraction * shading_derate_factor), where
            shaded_fraction = 1 - site.shading.shading_score (the field
            is documented as 0=fully shaded..1=unobstructed, so the
            derate must scale with the SHADED fraction, not with
            shading_score directly — an unobstructed site gets zero
            derate, a fully shaded site gets the full factor). Read
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
from solarfit.packs import config_pack
from solarfit.providers.weather import WeatherProviderError, fetch_weather


def estimate_generation_kwh(site: Site, capacity_kwp: float, params: dict | None = None) -> dict:
    """GEN-01..06 + SHADE-03."""
    del params  # no generation-specific overrides needed yet; kept for signature stability
    method_notes: list[str] = []

    performance_adjustment = config_pack.get_performance_adjustment(site.site_type)  # GEN-03
    base_ratio = config_pack.get_default_performance_ratio() * performance_adjustment

    lng, lat = site.centroid["coordinates"]
    try:
        weather = fetch_weather(lat, lng)  # GEN-02
        reference_irradiance = config_pack.get_reference_irradiance_w_m2()
        multiplier_min, multiplier_max = config_pack.get_weather_refinement_multiplier_bounds()
        multiplier = weather["irradiance_w_m2"] / reference_irradiance
        multiplier = max(multiplier_min, min(multiplier_max, multiplier))
        specific_yield = config_pack.get_fallback_specific_yield_kwh_per_kwp() * multiplier
        method = "weather_refined"
        method_notes.append(f"weather-refined yield (irradiance {weather['irradiance_w_m2']:.0f} W/m2)")
    except WeatherProviderError as exc:
        # A dead weather API must never crash an assessment — degrade to
        # the fallback constant and say so, rather than silently guessing.
        specific_yield = config_pack.get_fallback_specific_yield_kwh_per_kwp()
        method = "fallback_constant"
        method_notes.append(f"weather provider unavailable ({exc}); used fallback specific yield")

    shading = site.shading  # SHADE-03
    if shading is not None and shading.source == "solar_api" and shading.shading_score is not None:
        derate_factor = config_pack.get_shading_derate_factor()
        shaded_fraction = 1 - shading.shading_score  # shading_score: 0=fully shaded .. 1=unobstructed
        performance_ratio = base_ratio * (1 - shaded_fraction * derate_factor)
        method_notes.append(f"shading derate applied (score={shading.shading_score}, factor={derate_factor})")
    else:
        performance_ratio = base_ratio
        method_notes.append("shading unavailable — no derate applied (not assumed unshaded)")

    estimated_kwh_per_year = capacity_kwp * specific_yield * performance_ratio  # GEN-01

    return {
        "estimated_kwh_per_year": estimated_kwh_per_year,
        "specific_yield_kwh_per_kwp": specific_yield,
        "performance_ratio": performance_ratio,
        "method": method,  # GEN-05
        "method_notes": "; ".join(method_notes),
        "p50_kwh_per_year": None,  # GEN-06, deferred
        "p90_kwh_per_year": None,  # GEN-06, deferred
        "detailed_estimate": None,  # GEN-04, deferred
    }
