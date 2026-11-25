"""NASA POWER API client — keyless irradiance fallback for GEN-02.

Provider: NASA POWER (https://power.larc.nasa.gov/). No API key/signup,
public and free, global coverage including India. Unlike PVGIS's PVcalc,
this endpoint has no tilt/azimuth/system-loss inputs — it only returns
long-term climatology irradiance, so it can't stand in for the PVGIS
annual-kWh cross-check. It's the same kind of figure Open-Meteo's
fetch_weather() supplies for GEN-02: used in engine/generation.py as a
fallback irradiance source when Open-Meteo is unavailable, before
degrading further to the flat fallback specific yield constant.

fetch_nasa_power_irradiance() returns a small normalized dict so
solarfit.engine.generation never depends on NASA POWER's specific
response shape.
"""

import httpx

_BASE_URL = "https://power.larc.nasa.gov/api/temporal/climatology/point"
_TIMEOUT_SECONDS = 5.0


class NASAPowerError(Exception):
    """Raised on any failure to fetch or parse NASA POWER data. Callers
    (engine/generation.py) catch this specifically and degrade further to
    the flat fallback specific yield — a dead NASA POWER API must never
    crash an assessment."""


def fetch_nasa_power_irradiance(
    lat: float, lng: float, *, client: httpx.Client | None = None
) -> dict:
    """GEN-02 fallback. Returns {"irradiance_w_m2": float}.

    Uses the ANN (annual-average) ALLSKY_SFC_SW_DWN climatology figure,
    given in kWh/m2/day, converted to an average W/m2 figure
    (kWh/m2/day * 1000 / 24) so it's directly comparable to Open-Meteo's
    shortwave_radiation and usable in the same reference_irradiance-based
    multiplier in engine/generation.py.

    NASA POWER uses -999 as a fill value for missing data; treated as a
    failure here since a negative irradiance is never physically real.
    """
    params = {
        "parameters": "ALLSKY_SFC_SW_DWN",
        "community": "RE",
        "longitude": lng,
        "latitude": lat,
        "format": "JSON",
    }
    try:
        if client is not None:
            response = client.get(_BASE_URL, params=params, timeout=_TIMEOUT_SECONDS)
        else:
            response = httpx.get(_BASE_URL, params=params, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
        annual_kwh_m2_day = float(
            payload["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]["ANN"]
        )
        if annual_kwh_m2_day < 0:
            raise ValueError(f"NASA POWER returned a fill value: {annual_kwh_m2_day}")
        return {"irradiance_w_m2": annual_kwh_m2_day * 1000 / 24}
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise NASAPowerError(f"NASA POWER request failed: {exc}") from exc
