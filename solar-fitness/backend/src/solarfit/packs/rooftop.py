"""Owner: Person 2 (Rules Engine).

Implements the rooftop constraint pack of CON-05 (§9.4) of
Solar_Fitness_Engine_Development_Document_v1.1: net-metering cap,
consumption-offset ceiling, transformer-headroom ceiling, structural
gate (stub for now), subsidy-tier cap.

For ROOFTOP_RESIDENTIAL / ROOFTOP_CI, the subsidy-tier cap consumes
Person 4's captured USN (solarfit.domain.site.Site.usn) as an input
value — it does not introduce a new constraint of its own. Build
against site.usn being None until Person 4 delivers the real field;
site.usn is already part of the frozen Site contract (Day 0), so this
never needs an interface change later.

Depends on: solarfit.domain.constraint.{Ceiling, Gate} (frozen, Day 0),
solarfit.domain.site.Site (frozen, Day 0).
"""

from solarfit.domain.constraint import Ceiling, Gate
from solarfit.domain.site import Site
from solarfit.packs import config_pack


def net_metering_cap(site: Site, params: dict, *, pack: str = "rooftop_v1") -> Ceiling:
    """CON-05. `sanctioned_load_kva` isn't on the frozen Site model, so it
    comes through `params` — the escape hatch Constraint.evaluate already
    provides for inputs the frozen contracts don't carry."""
    sanctioned_load_kva = params.get("sanctioned_load_kva")
    if sanctioned_load_kva is None:
        return Ceiling(
            constraint="net_metering_cap",
            ceiling_kwp=None,
            reason="sanctioned_load_kva not provided",
            kind="regulatory",
            status="insufficient_data",
        )
    ratio = config_pack.get_net_metering_export_ratio(pack=pack)
    return Ceiling(
        constraint="net_metering_cap",
        ceiling_kwp=sanctioned_load_kva * ratio,
        reason=f"{ratio:.0%} of sanctioned load {sanctioned_load_kva} kVA",
        kind="regulatory",
        status="ok",
    )


def consumption_offset_ceiling(site: Site, params: dict) -> Ceiling:
    """CON-05."""
    annual_consumption_kwh = params.get("annual_consumption_kwh")
    if annual_consumption_kwh is None:
        return Ceiling(
            constraint="consumption_offset",
            ceiling_kwp=None,
            reason="annual_consumption_kwh not provided",
            kind="commercial",
            status="insufficient_data",
        )
    target_ratio = config_pack.get_consumption_offset_target_ratio()
    assumed_yield = config_pack.get_consumption_offset_assumed_yield()
    ceiling_kwp = (annual_consumption_kwh * target_ratio) / assumed_yield
    return Ceiling(
        constraint="consumption_offset",
        ceiling_kwp=ceiling_kwp,
        reason=f"sized to offset {target_ratio:.0%} of {annual_consumption_kwh} kWh/yr consumption",
        kind="commercial",
        status="ok",
    )


def transformer_headroom_ceiling(site: Site, params: dict) -> Ceiling:
    """CON-05."""
    transformer_kva = params.get("transformer_kva")
    if transformer_kva is None:
        return Ceiling(
            constraint="transformer_headroom",
            ceiling_kwp=None,
            reason="transformer_kva not provided",
            kind="physical",
            status="insufficient_data",
        )
    max_fraction = config_pack.get_transformer_headroom_max_fraction()
    return Ceiling(
        constraint="transformer_headroom",
        ceiling_kwp=transformer_kva * max_fraction,
        reason=f"{max_fraction:.0%} of transformer capacity {transformer_kva} kVA",
        kind="physical",
        status="ok",
    )


def structural_gate(site: Site, params: dict) -> Gate:
    """Stub for now, per CON-05 — a real structural assessment is out of
    scope for this pass. PENDING, never a crash, never a fabricated
    PASS/FAIL."""
    return Gate(
        gate="structural",
        status="PENDING",
        detail="structural assessment not yet implemented",
    )


def subsidy_tier_cap(site: Site, params: dict) -> Ceiling:
    """CON-05. Consumes site.usn (may be None until Person 4 delivers
    USN-02/03) — the consumer-category tier itself isn't on the frozen
    UsnCapture model, so it comes through params the same way."""
    if site.usn is None or site.usn.usn is None:
        return Ceiling(
            constraint="subsidy_tier_cap",
            ceiling_kwp=None,
            reason="USN not yet captured",
            kind="commercial",
            status="insufficient_data",
        )
    tier = params.get("consumer_category", "UNKNOWN")
    cap_kwp = config_pack.get_subsidy_tier_cap(tier)
    if cap_kwp is None:
        return Ceiling(
            constraint="subsidy_tier_cap",
            ceiling_kwp=None,
            reason=f"no subsidy tier cap configured for category '{tier}'",
            kind="commercial",
            status="insufficient_data",
        )
    return Ceiling(
        constraint="subsidy_tier_cap",
        ceiling_kwp=cap_kwp,
        reason=f"subsidy tier cap for category '{tier}'",
        kind="commercial",
        status="ok",
    )
