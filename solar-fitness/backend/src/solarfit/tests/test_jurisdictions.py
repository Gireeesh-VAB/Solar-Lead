"""§16 Testing — CON-08: a jurisdiction pack overrides a national default
with zero engine-code changes.
"""

from solarfit.packs import rooftop
from solarfit.packs.jurisdictions import in_ap


def test_in_ap_override_produces_stricter_ceiling_than_base_pack(make_site):
    site = make_site(jurisdiction="AP")
    params = {"sanctioned_load_kva": 10.0}

    base = rooftop.net_metering_cap(site, params)
    override = in_ap.net_metering_cap(site, params)

    assert override.ceiling_kwp < base.ceiling_kwp
