"""Weather API client — Person 2 (Rules Engine).

Provider: Open-Meteo (https://open-meteo.com/). No API key/signup and a
generous free tier, unlike OpenWeatherMap (solar radiation gated behind a
paid tier) or IMD (no self-serve access) — its "current" block already
carries shortwave radiation, temperature and cloud cover directly, a
direct match for GEN-02/04.

fetch_weather() returns a small normalized dict so
solarfit.engine.generation never depends on Open-Meteo's specific response
shape — swapping providers later stays a one-file change here.
"""

import httpx

_BASE_URL = "https://api.open-meteo.com/v1/forecast"
_CURRENT_FIELDS = "shortwave_radiation,temperature_2m,cloud_cover"
_TIMEOUT_SECONDS = 5.0


class WeatherProviderError(Exception):
    """Raised on any failure to fetch or parse weather data. Callers
    (engine/generation.py) catch this specifically and degrade to a
    fallback yield — a dead weather API must never crash an assessment."""


def fetch_weather(lat: float, lng: float) -> dict:
    """GEN-02/04. Returns {irradiance_w_m2, temperature_c, cloud_cover_pct}."""
    params = {"latitude": lat, "longitude": lng, "current": _CURRENT_FIELDS, "timezone": "UTC"}
    try:
        response = httpx.get(_BASE_URL, params=params, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        current = response.json()["current"]
        return {
            "irradiance_w_m2": float(current["shortwave_radiation"]),
            "temperature_c": float(current["temperature_2m"]),
            "cloud_cover_pct": float(current["cloud_cover"]),
        }
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise WeatherProviderError(f"Open-Meteo request failed: {exc}") from exc
