"""§16 Testing — generation (GEN-01..06) and the SHADE-03 derate. No live
weather calls: fetch_weather is monkeypatched at the module boundary
solarfit.engine.generation imports it through.
"""

import pytest
import yaml

import solarfit.engine.generation as generation
from solarfit.domain.site import ShadingEstimate
from solarfit.packs import config_pack


def _fake_weather(irradiance_w_m2=600.0):
    return lambda lat, lng: {
        "irradiance_w_m2": irradiance_w_m2,
        "temperature_c": 25.0,
        "cloud_cover_pct": 0.0,
    }


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


def test_gen04_gen06_explicitly_deferred(make_site, monkeypatch):
    monkeypatch.setattr(generation, "fetch_weather", _fake_weather())
    site = make_site()
    result = generation.estimate_generation_kwh(site, capacity_kwp=10.0)
    assert result["p50_kwh_per_year"] is None
    assert result["p90_kwh_per_year"] is None
    assert result["detailed_estimate"] is None

