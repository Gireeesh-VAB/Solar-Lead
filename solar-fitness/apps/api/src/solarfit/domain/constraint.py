"""Shared contract — built Day 0, frozen for the whole team.

Backs §9.4 Constraints (CON-01..09) and §9.5 Capacity Resolver
(CAP-01..06) of Solar_Fitness_Engine_Development_Document_v1.1.

`resolve_capacity` is reproduced verbatim from §12 — Person 2 implements
the real version in engine/resolver.py; this copy exists only so the
shape is frozen and importable from day one. Per §17: the resolver must
never grow site-type conditionals.
"""

from typing import Literal, Protocol

from pydantic import BaseModel

from solarfit.domain.site import Site


class Ceiling(BaseModel):
    constraint: str
    ceiling_kwp: float | None  # None = could not evaluate
    reason: str
    confidence_delta: float = 0.0
    kind: Literal["physical", "regulatory", "commercial"] = "physical"
    status: Literal["ok", "estimated", "insufficient_data", "not_applicable"]


class Gate(BaseModel):
    """CON-03. Binary, never enters the capacity minimum, modifies the verdict."""

    gate: str
    status: Literal["PASS", "FAIL", "PENDING"]
    detail: str


class Constraint(Protocol):
    id: str
    applies_to: list[str]  # site types
    jurisdiction: str | None

    def evaluate(self, site: Site, usable_area_m2: float, params: dict) -> Ceiling | Gate: ...


class CapacityResult(BaseModel):
    recommended_kwp: float | None
    max_technical_kwp: float | None = None
    binding_constraint: str | None = None
    headroom_kwp: float = 0.0
    ceilings: list[Ceiling] = []
    unit_basis: Literal["DC"] = "DC"
    status: Literal["ok", "INSUFFICIENT_DATA"] = "ok"
