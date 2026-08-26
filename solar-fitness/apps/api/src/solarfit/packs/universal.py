"""STUB — Owner: Person 2 (Rules Engine).

Implements the universal constraints of CON-07 (§9.4) of
Solar_Fitness_Engine_Development_Document_v1.1: usable-area ceiling
(pass-through of Person 1's engine/area.py output), evacuation-headroom
ceiling (nearest-substation PostGIS query, §14), minimum-viable-size
gate (read minimum_viable_kwp from
solarfit.packs.config_pack.get_minimum_viable_kwp()).

Depends on: solarfit.domain.constraint.{Ceiling, Gate} (frozen, Day 0),
solarfit.packs.config_pack (frozen loader, Day 0).
"""

from solarfit.domain.constraint import Ceiling, Gate
from solarfit.domain.site import Site


def usable_area_ceiling(site: Site, usable_area_m2: float) -> Ceiling:
    """Raises NotImplementedError until Person 2 implements it."""
    raise NotImplementedError


def evacuation_headroom_ceiling(site: Site, params: dict) -> Ceiling:
    """Raises NotImplementedError until Person 2 implements it."""
    raise NotImplementedError


def minimum_viable_size_gate(site: Site, usable_area_m2: float) -> Gate:
    """CON-07. Raises NotImplementedError until Person 2 implements it."""
    raise NotImplementedError
