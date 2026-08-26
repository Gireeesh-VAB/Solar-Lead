"""STUB — Owner: Person 2 (Rules Engine).

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


def net_metering_cap(site: Site, params: dict) -> Ceiling:
    """Raises NotImplementedError until Person 2 implements it."""
    raise NotImplementedError


def consumption_offset_ceiling(site: Site, params: dict) -> Ceiling:
    """Raises NotImplementedError until Person 2 implements it."""
    raise NotImplementedError


def transformer_headroom_ceiling(site: Site, params: dict) -> Ceiling:
    """Raises NotImplementedError until Person 2 implements it."""
    raise NotImplementedError


def structural_gate(site: Site, params: dict) -> Gate:
    """Stub for now, per CON-05."""
    raise NotImplementedError


def subsidy_tier_cap(site: Site, params: dict) -> Ceiling:
    """Consumes site.usn (may be None until Person 4 delivers USN-02/03)."""
    raise NotImplementedError
