"""PVGIS API client — independent PV yield cross-check.

Provider: PVGIS (EU JRC, https://re.jrc.ec.europa.eu/). No API key/signup,
public and free; covers India via NASA/ERA5 irradiance data. Used to
cross-validate the Solar API's own generation estimate rather than relying
on a single source (per the architecture doc's Section 4).

fetch_pvgis_generation() returns a small normalized dict so
solarfit.engine.generation never depends on PVGIS's specific response
shape — swapping/adding cross-check providers later stays a one-file change.
"""

import httpx

_BASE_URL = "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc"
_TIMEOUT_SECONDS = 5.0


class PVGISError(Exception):
    """Raised on any failure to fetch or parse PVGIS data. Callers
    (engine/generation.py) catch this specifically and degrade to the
    Solar-API-only estimate — a dead PVGIS API must never crash an
    assessment."""


def fetch_pvgis_generation(
    lat: float,
    lng: float,
    peak_power_kwp: float,
    loss_pct: float,
    tilt_deg: float,
    azimuth_deg: float,
    *,
    client: httpx.Client | None = None,
) -> dict:
    """Independent PV yield cross-check via PVGIS PVcalc.

    azimuth_deg is in the same compass-bearing convention used everywhere
    else in this codebase (Solar API's roofSegmentStats.azimuthDegrees:
    0=North, 90=East, 180=South, 270=West) — PVGIS's own `aspect` param
    uses a different convention (0=South, -90=East, 90=West, range
    -180..180), so it's converted here rather than leaking PVGIS's
    convention out to every caller. A raw pass-through (confirmed against
    the live API) gets rejected with a 400 for any azimuth above 180.

    Returns {"annual_kwh": float, "monthly_kwh": list[float]}.
    """
    aspect_deg = azimuth_deg - 180.0  # 0..360 compass -> -180..180, 0=South
    params = {
        "lat": lat,
        "lon": lng,
        "peakpower": peak_power_kwp,
        "loss": loss_pct,
        "angle": tilt_deg,
        "aspect": aspect_deg,
        "outputformat": "json",
    }
    try:
        if client is not None:
            response = client.get(_BASE_URL, params=params, timeout=_TIMEOUT_SECONDS)
        else:
            response = httpx.get(_BASE_URL, params=params, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        outputs = response.json()["outputs"]
        annual_kwh = float(outputs["totals"]["fixed"]["E_y"])
        monthly_kwh = [float(month["E_m"]) for month in outputs["monthly"]["fixed"]]
        return {"annual_kwh": annual_kwh, "monthly_kwh": monthly_kwh}
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise PVGISError(f"PVGIS request failed: {exc}") from exc
