"""Owner: Person 2 (Rules Engine).

Implements the universal constraints of CON-07 (§9.4) of
Solar_Fitness_Engine_Development_Document_v1.1: usable-area ceiling
(pass-through of Person 1's engine/area.py output), evacuation-headroom
ceiling (nearest-substation PostGIS query, §14), minimum-viable-size
gate (read minimum_viable_kwp from
solarfit.packs.config_pack.get_minimum_viable_kwp()).

Depends on: solarfit.domain.constraint.{Ceiling, Gate} (frozen, Day 0),
solarfit.packs.config_pack (frozen loader, Day 0).
"""

from solarfit import db
from solarfit.domain.constraint import Ceiling, Gate
from solarfit.domain.site import Site
from solarfit.packs import config_pack
from solarfit.repositories.substations import find_nearest_with_headroom


def usable_area_ceiling(site: Site, usable_area_m2: float) -> Ceiling:
    """CON-07. Wraps Person 1's usable-area figure as a physical ceiling."""
    density = config_pack.get_capacity_density_kwp_per_m2()
    return Ceiling(
        constraint="usable_area",
        ceiling_kwp=usable_area_m2 * density,
        reason=f"{usable_area_m2:.1f} m2 usable area at {density} kWp/m2",
        kind="physical",
        status="ok",
    )


def evacuation_headroom_ceiling(site: Site, params: dict) -> Ceiling:
    """CON-07. Nearest-substation-with-headroom query per §14, via
    repositories/substations.py + db.session_scope(). find_nearest_with_headroom
    is imported by name (not called as db.session_scope().find_...) so
    tests can monkeypatch it directly without touching the database.

    Never crashes: a down/misconfigured database, or no substation with
    spare capacity nearby, both degrade to insufficient_data — same
    discipline as providers/weather.py's failure handling.
    """
    lng, lat = site.centroid["coordinates"]
    try:
        with db.session_scope() as session:
            nearest = find_nearest_with_headroom(session, lat, lng)
    except Exception as exc:
        return Ceiling(
            constraint="evacuation_headroom",
            ceiling_kwp=None,
            reason=f"substation data source unavailable: {exc}",
            kind="physical",
            status="insufficient_data",
        )

    if not nearest:
        return Ceiling(
            constraint="evacuation_headroom",
            ceiling_kwp=None,
            reason="no substation with spare capacity found nearby",
            kind="physical",
            status="insufficient_data",
        )

    closest = nearest[0]
    return Ceiling(
        constraint="evacuation_headroom",
        ceiling_kwp=closest.spare_capacity_mw * 1000,
        reason=f"{closest.spare_capacity_mw} MW spare at {closest.name}, {closest.distance_m:.0f} m away",
        kind="physical",
        status="ok",
    )


def minimum_viable_size_gate(site: Site, usable_area_m2: float) -> Gate:
    """CON-07."""
    density = config_pack.get_capacity_density_kwp_per_m2()
    implied_kwp = usable_area_m2 * density
    minimum_kwp = config_pack.get_minimum_viable_kwp()

    if implied_kwp >= minimum_kwp:
        return Gate(
            gate="minimum_viable_size",
            status="PASS",
            detail=f"{implied_kwp:.2f} kWp >= minimum viable {minimum_kwp} kWp",
        )
    return Gate(
        gate="minimum_viable_size",
        status="FAIL",
        detail=f"{implied_kwp:.2f} kWp < minimum viable {minimum_kwp} kWp",
    )
