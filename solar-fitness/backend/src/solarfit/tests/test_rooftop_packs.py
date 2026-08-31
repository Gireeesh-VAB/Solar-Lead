"""§16 Testing — rooftop constraint pack (CON-05): net-metering cap,
consumption-offset ceiling, transformer-headroom ceiling, structural
gate (permanent stub), subsidy-tier cap.
"""

import pytest

from solarfit.domain.site import UsnCapture
from solarfit.packs import config_pack, rooftop


@pytest.fixture(autouse=True)
def _clear_pack_cache():
    config_pack.load_pack.cache_clear()
    yield
    config_pack.load_pack.cache_clear()


def test_net_metering_cap_happy_path(make_site):
    site = make_site()
    ceiling = rooftop.net_metering_cap(site, params={"sanctioned_load_kva": 10.0})
    assert ceiling.status == "ok"
    assert ceiling.ceiling_kwp == pytest.approx(10.0 * config_pack.get_net_metering_export_ratio())


def test_net_metering_cap_insufficient_data_without_sanctioned_load(make_site):
    site = make_site()
    ceiling = rooftop.net_metering_cap(site, params={})
    assert ceiling.ceiling_kwp is None
    assert ceiling.status == "insufficient_data"


def test_consumption_offset_ceiling_happy_path(make_site):
    site = make_site()
    ceiling = rooftop.consumption_offset_ceiling(site, params={"annual_consumption_kwh": 1400.0})
    assert ceiling.status == "ok"
    assert ceiling.ceiling_kwp == pytest.approx(1.0)  # 1400 kWh / 1400 kWh-per-kWp fallback yield


def test_consumption_offset_ceiling_insufficient_data(make_site):
    site = make_site()
    ceiling = rooftop.consumption_offset_ceiling(site, params={})
    assert ceiling.status == "insufficient_data"


def test_transformer_headroom_ceiling_happy_path(make_site):
    site = make_site()
    ceiling = rooftop.transformer_headroom_ceiling(site, params={"transformer_kva": 100.0})
    assert ceiling.status == "ok"
    assert ceiling.ceiling_kwp == pytest.approx(
        100.0 * config_pack.get_transformer_headroom_max_fraction()
    )


def test_transformer_headroom_ceiling_insufficient_data(make_site):
    site = make_site()
    ceiling = rooftop.transformer_headroom_ceiling(site, params={})
    assert ceiling.status == "insufficient_data"


def test_structural_gate_never_raises(make_site):
    site = make_site()
    gate = rooftop.structural_gate(site, params={})
    assert gate.status == "PENDING"


def test_subsidy_tier_cap_insufficient_data_without_usn(make_site):
    site = make_site(usn=None)
    ceiling = rooftop.subsidy_tier_cap(site, params={})
    assert ceiling.status == "insufficient_data"


def test_subsidy_tier_cap_with_usn_and_known_category(make_site):
    site = make_site(usn=UsnCapture(usn="AP123456", usn_source="manual"))
    ceiling = rooftop.subsidy_tier_cap(site, params={"consumer_category": "DOMESTIC"})
    assert ceiling.status == "ok"
    assert ceiling.ceiling_kwp == config_pack.get_subsidy_tier_cap("DOMESTIC")


def test_subsidy_tier_cap_with_usn_but_unknown_category(make_site):
    site = make_site(usn=UsnCapture(usn="AP123456", usn_source="manual"))
    ceiling = rooftop.subsidy_tier_cap(site, params={"consumer_category": "UNKNOWN"})
    assert ceiling.status == "insufficient_data"
