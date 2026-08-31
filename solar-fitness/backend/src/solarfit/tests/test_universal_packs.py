"""§16 Testing — universal constraint pack (CON-07): usable-area ceiling,
evacuation-headroom ceiling, minimum-viable-size gate.
"""

import os

import pytest

from solarfit.packs import config_pack, universal


@pytest.fixture(autouse=True)
def _clear_pack_cache():
    config_pack.load_pack.cache_clear()
    yield
    config_pack.load_pack.cache_clear()


def test_usable_area_ceiling_converts_area_to_kwp(make_site):
    site = make_site()
    density = config_pack.get_capacity_density_kwp_per_m2()

    ceiling = universal.usable_area_ceiling(site, usable_area_m2=100.0)

    assert ceiling.constraint == "usable_area"
    assert ceiling.kind == "physical"
    assert ceiling.status == "ok"
    assert ceiling.ceiling_kwp == pytest.approx(100.0 * density)


def test_evacuation_headroom_ceiling_ok_when_substation_found(make_site, monkeypatch):
    from solarfit.repositories.substations import NearestSubstation

    monkeypatch.setattr(
        universal,
        "find_nearest_with_headroom",
        lambda session, lat, lng, limit=5: [NearestSubstation(name="Test Substation", spare_capacity_mw=2.5, distance_m=450.0)],
    )

    ceiling = universal.evacuation_headroom_ceiling(make_site(), params={})

    assert ceiling.status == "ok"
    assert ceiling.kind == "physical"
    assert ceiling.ceiling_kwp == pytest.approx(2500.0)
    assert "Test Substation" in ceiling.reason


def test_evacuation_headroom_ceiling_insufficient_data_when_none_nearby(make_site, monkeypatch):
    monkeypatch.setattr(universal, "find_nearest_with_headroom", lambda session, lat, lng, limit=5: [])

    ceiling = universal.evacuation_headroom_ceiling(make_site(), params={})

    assert ceiling.ceiling_kwp is None
    assert ceiling.status == "insufficient_data"
    assert "no substation" in ceiling.reason


def test_evacuation_headroom_ceiling_insufficient_data_when_db_unavailable(make_site, monkeypatch):
    def _raise(session, lat, lng, limit=5):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(universal, "find_nearest_with_headroom", _raise)

    ceiling = universal.evacuation_headroom_ceiling(make_site(), params={})

    assert ceiling.ceiling_kwp is None
    assert ceiling.status == "insufficient_data"
    assert "unavailable" in ceiling.reason


def test_minimum_viable_size_gate_pass(make_site, tmp_path):
    site = make_site()
    _write_test_pack(tmp_path, minimum_viable_kwp=1.0, capacity_density_kwp_per_m2=0.2)

    os.environ["SOLARFIT_CONFIG_PACKS_DIR"] = str(tmp_path)
    config_pack.load_pack.cache_clear()
    try:
        gate = universal.minimum_viable_size_gate(site, usable_area_m2=100.0)  # implies 20 kWp
        assert gate.status == "PASS"
    finally:
        del os.environ["SOLARFIT_CONFIG_PACKS_DIR"]


def test_minimum_viable_size_gate_fail(make_site, tmp_path):
    site = make_site()
    _write_test_pack(tmp_path, minimum_viable_kwp=50.0, capacity_density_kwp_per_m2=0.2)

    os.environ["SOLARFIT_CONFIG_PACKS_DIR"] = str(tmp_path)
    config_pack.load_pack.cache_clear()
    try:
        gate = universal.minimum_viable_size_gate(site, usable_area_m2=10.0)  # implies 2 kWp
        assert gate.status == "FAIL"
    finally:
        del os.environ["SOLARFIT_CONFIG_PACKS_DIR"]


def _write_test_pack(tmp_path, **overrides):
    base = config_pack.load_pack("rooftop_v1")
    pack = {**base, **overrides}
    import yaml

    (tmp_path / "rooftop_v1.yaml").write_text(yaml.safe_dump(pack), encoding="utf-8")
