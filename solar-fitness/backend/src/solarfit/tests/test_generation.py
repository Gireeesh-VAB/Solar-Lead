"""§16 Testing — generation (GEN-01..06) and the SHADE-03 derate. No live
weather/PVGIS calls: fetch_weather and fetch_pvgis_generation are
monkeypatched at the module boundary solarfit.engine.generation imports
them through.
"""

import pytest
import yaml

from solarfit.domain.site import ShadingEstimate
from solarfit.engine import generation
from solarfit.packs import config_pack
from solarfit.providers.nasa_power import NASAPowerError
from solarfit.providers.pvgis import PVGISError


def _fake_weather(irradiance_w_m2=600.0):
    return lambda lat, lng: {
        "irradiance_w_m2": irradiance_w_m2,
        "temperature_c": 25.0,
        "cloud_cover_pct": 0.0,
    }


def _fake_pvgis(annual_kwh=9000.0):
    return lambda *args, **kwargs: {
        "annual_kwh": annual_kwh,
        "monthly_kwh": [annual_kwh / 12] * 12,
    }


def _raise_pvgis(*args, **kwargs):
    raise PVGISError("boom")


def _fake_nasa_power(irradiance_w_m2=600.0):
    return lambda lat, lng: {"irradiance_w_m2": irradiance_w_m2}


def _raise_nasa_power(*args, **kwargs):
    raise NASAPowerError("boom")


@pytest.fixture(autouse=True)
def _default_pvgis(monkeypatch):
    """Every test not explicitly exercising PVGIS behaviour gets a
    canned success response, so nothing here makes a live network call."""
    monkeypatch.setattr(generation, "fetch_pvgis_generation", _fake_pvgis())


@pytest.fixture(autouse=True)
def _default_nasa_power(monkeypatch):
    """Every test not explicitly exercising the NASA POWER fallback gets
    a failure by default (it's only ever reached when weather already
    failed), so nothing here makes a live network call and the existing
    weather-unavailable tests keep degrading all the way to the flat
    fallback constant."""
    monkeypatch.setattr(generation, "fetch_nasa_power_irradiance", _raise_nasa_power)


def test_gen01_fast_estimate_formula(make_site, monkeypatch):
    monkeypatch.setattr(generation, "fetch_weather", _fake_weather())
    site = make_site()

    result = generation.estimate_generation_kwh(site, capacity_kwp=10.0)

    assert result["estimated_kwh_per_year"] == pytest.approx(10.0 * 1400.0 * 0.8)
    assert result["method"] == "weather_refined"


def test_gen02_falls_back_gracefully_when_weather_unavailable(make_site, monkeypatch):
    def _raise(lat, lng):
        raise generation.WeatherProviderError("boom")

    monkeypatch.setattr(generation, "fetch_weather", _raise)
    site = make_site()

    result = generation.estimate_generation_kwh(site, capacity_kwp=10.0)

    assert result["method"] == "fallback_constant"
    assert "weather provider unavailable" in result["method_notes"]
    assert result["estimated_kwh_per_year"] == pytest.approx(10.0 * 1400.0 * 0.8)


def test_gen02_falls_back_to_nasa_power_when_weather_unavailable(make_site, monkeypatch):
    def _raise(lat, lng):
        raise generation.WeatherProviderError("boom")

    monkeypatch.setattr(generation, "fetch_weather", _raise)
    monkeypatch.setattr(generation, "fetch_nasa_power_irradiance", _fake_nasa_power(660.0))
    site = make_site()

    result = generation.estimate_generation_kwh(site, capacity_kwp=10.0)

    assert result["method"] == "nasa_power_fallback"
    assert "NASA POWER climatology fallback" in result["method_notes"]
    # multiplier = 660/600 = 1.1 -> specific_yield = 1400 * 1.1 = 1540
    assert result["specific_yield_kwh_per_kwp"] == pytest.approx(1540.0)
    assert result["estimated_kwh_per_year"] == pytest.approx(10.0 * 1540.0 * 0.8)


def test_gen02_falls_back_to_flat_constant_when_both_unavailable(make_site, monkeypatch):
    def _raise(lat, lng):
        raise generation.WeatherProviderError("boom")

    monkeypatch.setattr(generation, "fetch_weather", _raise)
    monkeypatch.setattr(generation, "fetch_nasa_power_irradiance", _raise_nasa_power)
    site = make_site()

    result = generation.estimate_generation_kwh(site, capacity_kwp=10.0)

    assert result["method"] == "fallback_constant"
    assert "weather provider unavailable" in result["method_notes"]
    assert "NASA POWER fallback also unavailable" in result["method_notes"]
    assert result["estimated_kwh_per_year"] == pytest.approx(10.0 * 1400.0 * 0.8)


def test_gen03_site_type_adjustment_applied(make_site, monkeypatch, tmp_path):
    monkeypatch.setattr(generation, "fetch_weather", _fake_weather())
    base = config_pack.load_pack("rooftop_v1")
    pack = {**base, "performance_adjustment": {**base["performance_adjustment"], "ROOFTOP_RESIDENTIAL": 0.5}}
    (tmp_path / "rooftop_v1.yaml").write_text(yaml.safe_dump(pack), encoding="utf-8")
    monkeypatch.setenv("SOLARFIT_CONFIG_PACKS_DIR", str(tmp_path))
    config_pack.load_pack.cache_clear()

    site = make_site(site_type="ROOFTOP_RESIDENTIAL")
    result = generation.estimate_generation_kwh(site, capacity_kwp=10.0)

    assert result["performance_ratio"] == pytest.approx(0.8 * 0.5)
    config_pack.load_pack.cache_clear()


def test_gen05_method_recorded_in_every_result(make_site, monkeypatch):
    monkeypatch.setattr(generation, "fetch_weather", _fake_weather())
    site = make_site()
    result = generation.estimate_generation_kwh(site, capacity_kwp=10.0)
    assert result["method"]
    assert result["method_notes"]


def test_shade03_derate_applied_when_solar_api_source(make_site, monkeypatch, tmp_path):
    monkeypatch.setattr(generation, "fetch_weather", _fake_weather())
    base = config_pack.load_pack("rooftop_v1")
    pack = {**base, "shading_derate_factor": 0.5}
    (tmp_path / "rooftop_v1.yaml").write_text(yaml.safe_dump(pack), encoding="utf-8")
    monkeypatch.setenv("SOLARFIT_CONFIG_PACKS_DIR", str(tmp_path))
    config_pack.load_pack.cache_clear()

    site = make_site(shading=ShadingEstimate(shading_score=0.4, source="solar_api"))
    result = generation.estimate_generation_kwh(site, capacity_kwp=10.0)

    # shading_score=0.4 -> shaded_fraction=0.6 (0=fully shaded..1=unobstructed)
    assert result["performance_ratio"] == pytest.approx(0.8 * (1 - 0.6 * 0.5))
    assert "shading derate applied" in result["method_notes"]
    config_pack.load_pack.cache_clear()


def test_shade03_derate_direction_unobstructed_beats_fully_shaded(make_site, monkeypatch, tmp_path):
    """Regression test for a direction bug: an unobstructed site
    (shading_score=1) must never be derated more than a fully shaded one
    (shading_score=0) — the derate scales with the SHADED fraction."""
    monkeypatch.setattr(generation, "fetch_weather", _fake_weather())
    base = config_pack.load_pack("rooftop_v1")
    pack = {**base, "shading_derate_factor": 0.5}
    (tmp_path / "rooftop_v1.yaml").write_text(yaml.safe_dump(pack), encoding="utf-8")
    monkeypatch.setenv("SOLARFIT_CONFIG_PACKS_DIR", str(tmp_path))
    config_pack.load_pack.cache_clear()

    unobstructed = make_site(shading=ShadingEstimate(shading_score=1.0, source="solar_api"))
    fully_shaded = make_site(shading=ShadingEstimate(shading_score=0.0, source="solar_api"))

    unobstructed_ratio = generation.estimate_generation_kwh(unobstructed, capacity_kwp=10.0)["performance_ratio"]
    fully_shaded_ratio = generation.estimate_generation_kwh(fully_shaded, capacity_kwp=10.0)["performance_ratio"]

    assert unobstructed_ratio == pytest.approx(0.8)  # no derate at all
    assert fully_shaded_ratio == pytest.approx(0.8 * (1 - 0.5))  # full derate_factor applied
    assert unobstructed_ratio > fully_shaded_ratio
    config_pack.load_pack.cache_clear()


def test_shade03_no_derate_when_shading_unavailable(make_site, monkeypatch):
    monkeypatch.setattr(generation, "fetch_weather", _fake_weather())
    site = make_site(shading=None)

    result = generation.estimate_generation_kwh(site, capacity_kwp=10.0)

    assert result["performance_ratio"] == pytest.approx(0.8)
    assert "shading unavailable" in result["method_notes"]


def test_gen06_p50_p90_explicitly_deferred(make_site, monkeypatch):
    monkeypatch.setattr(generation, "fetch_weather", _fake_weather())
    site = make_site()
    result = generation.estimate_generation_kwh(site, capacity_kwp=10.0)
    assert result["p50_kwh_per_year"] is None
    assert result["p90_kwh_per_year"] is None
    assert result["detailed_estimate"] is None


def test_gen04_pvgis_cross_check_populates_result(make_site, monkeypatch):
    monkeypatch.setattr(generation, "fetch_weather", _fake_weather())
    monkeypatch.setattr(generation, "fetch_pvgis_generation", _fake_pvgis(annual_kwh=12345.0))
    site = make_site()

    result = generation.estimate_generation_kwh(site, capacity_kwp=10.0)

    assert result["pvgis_annual_kwh"] == 12345.0
    assert result["pvgis_monthly_kwh"] == [12345.0 / 12] * 12
    assert "PVGIS cross-check" in result["method_notes"]


def test_gen04_pvgis_degrades_gracefully_on_error(make_site, monkeypatch):
    monkeypatch.setattr(generation, "fetch_weather", _fake_weather())
    monkeypatch.setattr(generation, "fetch_pvgis_generation", _raise_pvgis)
    site = make_site()

    result = generation.estimate_generation_kwh(site, capacity_kwp=10.0)

    assert result["pvgis_annual_kwh"] is None
    assert result["pvgis_monthly_kwh"] is None
    assert "PVGIS cross-check unavailable" in result["method_notes"]
    # The rest of the estimate must be unaffected by a dead PVGIS call.
    assert result["estimated_kwh_per_year"] == pytest.approx(10.0 * 1400.0 * 0.8)


def test_gen04_uses_caller_tilt_azimuth_when_given(make_site, monkeypatch):
    monkeypatch.setattr(generation, "fetch_weather", _fake_weather())
    captured = {}

    def _capture(lat, lng, capacity_kwp, *, loss_pct, tilt_deg, azimuth_deg):
        captured["tilt_deg"] = tilt_deg
        captured["azimuth_deg"] = azimuth_deg
        return {"annual_kwh": 1000.0, "monthly_kwh": [83.3] * 12}

    monkeypatch.setattr(generation, "fetch_pvgis_generation", _capture)
    site = make_site()

    result = generation.estimate_generation_kwh(
        site, capacity_kwp=10.0, params={"tilt_deg": 22.0, "azimuth_deg": 90.0}
    )

    assert captured["tilt_deg"] == 22.0
    assert captured["azimuth_deg"] == 90.0
    assert "default tilt/azimuth" not in result["method_notes"]


def test_gen04_falls_back_to_default_tilt_azimuth_when_absent(make_site, monkeypatch):
    monkeypatch.setattr(generation, "fetch_weather", _fake_weather())
    captured = {}

    def _capture(lat, lng, capacity_kwp, *, loss_pct, tilt_deg, azimuth_deg):
        captured["tilt_deg"] = tilt_deg
        captured["azimuth_deg"] = azimuth_deg
        return {"annual_kwh": 1000.0, "monthly_kwh": [83.3] * 12}

    monkeypatch.setattr(generation, "fetch_pvgis_generation", _capture)
    site = make_site()

    result = generation.estimate_generation_kwh(site, capacity_kwp=10.0)

    lng, lat = site.centroid["coordinates"]
    assert captured["tilt_deg"] == pytest.approx(abs(lat))
    assert captured["azimuth_deg"] == 180.0  # south-facing, compass convention (0=N)
    assert "default tilt/azimuth" in result["method_notes"]


def test_low_primary_plane_coverage_adds_a_partial_match_caveat(make_site, monkeypatch):
    """The tilt/azimuth plane only covers part of the customer's own
    selected/cropped area (e.g. their crop spans two Google segments and
    panels concentrated on one) — this must still be used (it's the best
    signal available), but the customer must be told it's a partial
    match, not silently presented as describing their whole roof."""
    monkeypatch.setattr(generation, "fetch_weather", _fake_weather())
    monkeypatch.setattr(
        generation, "fetch_pvgis_generation", lambda *a, **k: {"annual_kwh": 1000.0, "monthly_kwh": [83.3] * 12}
    )
    site = make_site()

    result = generation.estimate_generation_kwh(
        site,
        capacity_kwp=10.0,
        params={"tilt_deg": 22.0, "azimuth_deg": 90.0, "primary_plane_coverage_ratio": 0.3},
    )

    assert "only part of your selected area" in result["method_notes"]
    assert "30%" in result["method_notes"]


def test_high_primary_plane_coverage_adds_no_caveat(make_site, monkeypatch):
    monkeypatch.setattr(generation, "fetch_weather", _fake_weather())
    monkeypatch.setattr(
        generation, "fetch_pvgis_generation", lambda *a, **k: {"annual_kwh": 1000.0, "monthly_kwh": [83.3] * 12}
    )
    site = make_site()

    result = generation.estimate_generation_kwh(
        site,
        capacity_kwp=10.0,
        params={"tilt_deg": 22.0, "azimuth_deg": 90.0, "primary_plane_coverage_ratio": 0.95},
    )

    assert "only part of your selected area" not in result["method_notes"]


def test_missing_primary_plane_coverage_ratio_adds_no_caveat(make_site, monkeypatch):
    """No coverage-ratio signal at all (an older caller, or genuinely
    nothing to compare against) must not fabricate a partial-match
    warning — same "never guess" discipline as everywhere else in this
    module."""
    monkeypatch.setattr(generation, "fetch_weather", _fake_weather())
    monkeypatch.setattr(
        generation, "fetch_pvgis_generation", lambda *a, **k: {"annual_kwh": 1000.0, "monthly_kwh": [83.3] * 12}
    )
    site = make_site()

    result = generation.estimate_generation_kwh(
        site, capacity_kwp=10.0, params={"tilt_deg": 22.0, "azimuth_deg": 90.0}
    )

    assert "only part of your selected area" not in result["method_notes"]
