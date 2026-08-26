"""STUB — Owner: Person 2 (Rules Engine).

Typed client for the chosen Weather API (irradiance, temperature, cloud
cover by lat/lng) — feeds GEN-02/04 (§9.6 Generation) and the ML feature
set (§9.13). Provider selection (OpenWeatherMap / Visual Crossing / IMD
etc.) is an open decision per §10.3 — flagged there, not hard-picked.

Depends on: solarfit.config.get_settings() for WEATHER_API_KEY (frozen,
Day 0).
"""

def fetch_weather(lat: float, lng: float) -> dict:
    """Raises NotImplementedError until Person 2 implements it."""
    raise NotImplementedError
