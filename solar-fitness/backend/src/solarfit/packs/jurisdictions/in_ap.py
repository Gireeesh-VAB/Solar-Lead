"""CON-08 worked example — Person 2.

Andhra Pradesh's net-metering export ratio is stricter than the national
default in rooftop_v1.yaml. Same function shape as
solarfit.packs.rooftop.net_metering_cap, reading a separate
jurisdiction-scoped pack instead — proves a jurisdiction can override a
national default with zero changes to engine/resolver.py, packs/rooftop.py,
or packs/registry.py beyond registering this function against
jurisdiction="AP".
"""

from solarfit.domain.constraint import Ceiling
from solarfit.domain.site import Site
from solarfit.packs import config_pack

PACK = "jurisdictions/in_ap"


def net_metering_cap(site: Site, params: dict) -> Ceiling:
    sanctioned_load_kva = params.get("sanctioned_load_kva")
    if sanctioned_load_kva is None:
        return Ceiling(
            constraint="net_metering_cap",
            ceiling_kwp=None,
            reason="sanctioned_load_kva not provided",
            kind="regulatory",
            status="insufficient_data",
        )
    ratio = config_pack.get_net_metering_export_ratio(pack=PACK)
    return Ceiling(
        constraint="net_metering_cap",
        ceiling_kwp=sanctioned_load_kva * ratio,
        reason=f"AP override: {ratio:.0%} of sanctioned load {sanctioned_load_kva} kVA",
        kind="regulatory",
        status="ok",
    )
