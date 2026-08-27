"""CON-02/08/09 — resolves the Constraint list to evaluate for a given
site_type + jurisdiction, and separates ceilings from gates (CON-03)
before anything reaches engine/resolver.py.

This is the one place a jurisdiction override is selected: a matching
override REPLACES the base entry with the same key rather than running
alongside it. Neither resolve_capacity() nor any individual constraint
function branches on jurisdiction or site type (§17) — only this module
does, and only to pick which functions to call.
"""

from collections.abc import Callable
from dataclasses import dataclass

from solarfit.domain.constraint import Ceiling, Gate
from solarfit.domain.site import RoofSiteType, Site
from solarfit.packs import rooftop, universal
from solarfit.packs.jurisdictions import in_ap

ConstraintFn = Callable[[Site, float, dict], Ceiling | Gate]

_ROOFTOP_TYPES: tuple[RoofSiteType, ...] = ("ROOFTOP_GOVT", "ROOFTOP_RESIDENTIAL", "ROOFTOP_CI")
_BILLING_LINKED_TYPES: tuple[RoofSiteType, ...] = ("ROOFTOP_RESIDENTIAL", "ROOFTOP_CI")


@dataclass(frozen=True)
class _Entry:
    key: str
    fn: ConstraintFn
    applies_to: tuple[RoofSiteType, ...]
    jurisdiction: str | None = None


def _base_entries() -> list[_Entry]:
    return [
        _Entry("usable_area", lambda site, usable_area_m2, params: universal.usable_area_ceiling(
            site, usable_area_m2), applies_to=_ROOFTOP_TYPES),
        _Entry("evacuation_headroom", lambda site, usable_area_m2, params: universal.evacuation_headroom_ceiling(
            site, params), applies_to=_ROOFTOP_TYPES),
        _Entry("minimum_viable_size", lambda site, usable_area_m2, params: universal.minimum_viable_size_gate(
            site, usable_area_m2), applies_to=_ROOFTOP_TYPES),
        _Entry("net_metering_cap", lambda site, usable_area_m2, params: rooftop.net_metering_cap(
            site, params), applies_to=_BILLING_LINKED_TYPES),
        _Entry("consumption_offset", lambda site, usable_area_m2, params: rooftop.consumption_offset_ceiling(
            site, params), applies_to=_ROOFTOP_TYPES),
        _Entry("transformer_headroom", lambda site, usable_area_m2, params: rooftop.transformer_headroom_ceiling(
            site, params), applies_to=_ROOFTOP_TYPES),
        _Entry("structural", lambda site, usable_area_m2, params: rooftop.structural_gate(
            site, params), applies_to=_ROOFTOP_TYPES),
        _Entry("subsidy_tier_cap", lambda site, usable_area_m2, params: rooftop.subsidy_tier_cap(
            site, params), applies_to=_BILLING_LINKED_TYPES),
    ]


def _jurisdiction_overrides(jurisdiction: str | None) -> list[_Entry]:
    if jurisdiction == "AP":
        return [
            _Entry("net_metering_cap", in_ap.net_metering_cap,
                   applies_to=_BILLING_LINKED_TYPES, jurisdiction="AP"),
        ]
    return []


def resolve_constraint_fns(site_type: RoofSiteType, jurisdiction: str | None) -> list[ConstraintFn]:
    """CON-02. Order of the returned list is not meaningful — CON-09
    requires every constraint be evaluable independently and in any order."""
    entries: dict[str, _Entry] = {
        entry.key: entry for entry in _base_entries() if site_type in entry.applies_to
    }
    for override in _jurisdiction_overrides(jurisdiction):
        if site_type in override.applies_to:
            entries[override.key] = override
    return [entry.fn for entry in entries.values()]


def evaluate_all(site: Site, usable_area_m2: float, params: dict) -> tuple[list[Ceiling], list[Gate]]:
    """CON-03: split ceilings from gates here, before anything reaches
    engine/resolver.py — resolve_capacity() only ever sees Ceilings."""
    results = [fn(site, usable_area_m2, params)
               for fn in resolve_constraint_fns(site.site_type, site.jurisdiction)]
    ceilings = [r for r in results if isinstance(r, Ceiling)]
    gates = [r for r in results if isinstance(r, Gate)]
    return ceilings, gates
