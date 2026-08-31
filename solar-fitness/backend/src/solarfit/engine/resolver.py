"""Owner: Person 2 (Rules Engine).

Implements §9.5 Capacity Resolver (CAP-01..06) of
Solar_Fitness_Engine_Development_Document_v1.1. The reference
implementation is given verbatim in §12 — reproduce it here nearly as-is;
per §17 it must NEVER grow site-type conditionals.

  CAP-01  recommended = minimum of all evaluable ceilings.
  CAP-02  Identify and return the binding constraint.
  CAP-03  max_technical = minimum of physical-only ceilings.
  CAP-04  headroom = gap between binding ceiling and the next lowest.
  CAP-05  Return the full ceiling list, not merely the minimum.
  CAP-06  unit_basis = "DC" explicitly.

Depends on: solarfit.domain.constraint.{Ceiling, CapacityResult}
(frozen, Day 0).
"""

from solarfit.domain.constraint import CapacityResult, Ceiling

_USABLE_STATUSES = {"ok", "estimated"}


def resolve_capacity(ceilings: list[Ceiling]) -> CapacityResult:
    """CAP-01..06."""
    # insufficient_data/not_applicable ceilings carry ceiling_kwp=None or a
    # value that isn't trustworthy — never coerce via `or 0`, that would let
    # an unevaluable constraint silently win the minimum.
    usable = [c for c in ceilings if c.ceiling_kwp is not None and c.status in _USABLE_STATUSES]

    if not usable:
        return CapacityResult(
            recommended_kwp=None,
            max_technical_kwp=None,
            binding_constraint=None,
            headroom_kwp=0.0,
            ceilings=ceilings,
            unit_basis="DC",
            status="INSUFFICIENT_DATA",
        )

    ordered = sorted(usable, key=lambda c: c.ceiling_kwp)
    binding = ordered[0]
    headroom_kwp = (ordered[1].ceiling_kwp - binding.ceiling_kwp) if len(ordered) > 1 else 0.0

    physical = [c for c in usable if c.kind == "physical"]
    max_technical_kwp = min((c.ceiling_kwp for c in physical), default=None)

    return CapacityResult(
        recommended_kwp=binding.ceiling_kwp,
        max_technical_kwp=max_technical_kwp,
        binding_constraint=binding.constraint,
        headroom_kwp=headroom_kwp,
        ceilings=ceilings,
        unit_basis="DC",
        status="ok",
    )
