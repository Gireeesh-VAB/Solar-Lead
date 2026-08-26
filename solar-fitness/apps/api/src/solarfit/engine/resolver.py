"""STUB — Owner: Person 2 (Rules Engine).

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


def resolve_capacity(ceilings: list[Ceiling]) -> CapacityResult:
    """CAP-01..06. Raises NotImplementedError until Person 2 implements it.

    See §12 for the full reference implementation to port in.
    """
    raise NotImplementedError
