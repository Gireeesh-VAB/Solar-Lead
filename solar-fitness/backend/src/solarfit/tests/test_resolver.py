"""§16 Testing — 'Resolver' row: recommended is always the minimum,
binding always matches, headroom never negative, all-null ceilings ->
INSUFFICIENT_DATA. Plus the CAP-01..06 details from the resolver's own
docstring/spec.
"""

import random

from solarfit.domain.constraint import Ceiling
from solarfit.engine.resolver import resolve_capacity


def _ceiling(constraint, ceiling_kwp, *, kind="physical", status="ok"):
    return Ceiling(constraint=constraint, ceiling_kwp=ceiling_kwp, reason="fixture", kind=kind, status=status)


def test_single_usable_ceiling_is_recommended():
    result = resolve_capacity([_ceiling("a", 10.0)])
    assert result.recommended_kwp == 10.0
    assert result.binding_constraint == "a"
    assert result.headroom_kwp == 0.0
    assert result.status == "ok"


def test_minimum_of_multiple_usable_ceilings_wins():
    result = resolve_capacity([_ceiling("a", 10.0), _ceiling("b", 5.0), _ceiling("c", 20.0)])
    assert result.recommended_kwp == 5.0
    assert result.binding_constraint == "b"


def test_insufficient_data_ceiling_excluded_from_minimum():
    result = resolve_capacity([
        _ceiling("a", None, status="insufficient_data"),
        _ceiling("b", 8.0),
    ])
    assert result.recommended_kwp == 8.0
    assert result.binding_constraint == "b"


def test_not_applicable_ceiling_excluded_from_minimum():
    result = resolve_capacity([
        _ceiling("a", 1.0, status="not_applicable"),
        _ceiling("b", 8.0),
    ])
    assert result.recommended_kwp == 8.0
    assert result.binding_constraint == "b"


def test_all_ceilings_unusable_returns_insufficient_data_status():
    ceilings = [
        _ceiling("a", None, status="insufficient_data"),
        _ceiling("b", 5.0, status="not_applicable"),
    ]
    result = resolve_capacity(ceilings)
    assert result.recommended_kwp is None
    assert result.status == "INSUFFICIENT_DATA"
    assert result.ceilings == ceilings  # CAP-05: full list, unfiltered, always


def test_max_technical_kwp_only_considers_physical_kind():
    result = resolve_capacity([
        _ceiling("physical", 15.0, kind="physical"),
        _ceiling("regulatory", 5.0, kind="regulatory"),
    ])
    assert result.recommended_kwp == 5.0  # regulatory is still the overall minimum
    assert result.max_technical_kwp == 15.0  # but max_technical ignores it


def test_headroom_is_gap_to_next_lowest_usable_ceiling():
    result = resolve_capacity([_ceiling("a", 5.0), _ceiling("b", 8.0), _ceiling("c", 20.0)])
    assert result.headroom_kwp == 3.0


def test_ceilings_field_returns_full_unfiltered_list():
    ceilings = [_ceiling("a", 5.0), _ceiling("b", None, status="insufficient_data")]
    result = resolve_capacity(ceilings)
    assert result.ceilings == ceilings


def test_unit_basis_is_always_dc():
    assert resolve_capacity([_ceiling("a", 5.0)]).unit_basis == "DC"
    assert resolve_capacity([]).unit_basis == "DC"


def test_resolve_capacity_is_order_independent():
    ceilings = [
        _ceiling("a", 12.0, kind="physical"),
        _ceiling("b", 7.0, kind="regulatory"),
        _ceiling("c", None, status="insufficient_data"),
        _ceiling("d", 9.0, kind="physical"),
        _ceiling("e", 3.0, status="not_applicable"),
    ]
    baseline = resolve_capacity(ceilings)
    rng = random.Random(42)
    for _ in range(20):
        shuffled = ceilings.copy()
        rng.shuffle(shuffled)
        result = resolve_capacity(shuffled)
        assert result.recommended_kwp == baseline.recommended_kwp
        assert result.max_technical_kwp == baseline.max_technical_kwp
        assert result.headroom_kwp == baseline.headroom_kwp
        assert result.binding_constraint == baseline.binding_constraint
        assert result.status == baseline.status


def test_resolve_capacity_is_pure():
    ceilings = [_ceiling("a", 12.0), _ceiling("b", 7.0)]
    snapshot = list(ceilings)

    first = resolve_capacity(ceilings)
    second = resolve_capacity(ceilings)

    assert first == second
    assert ceilings == snapshot  # input list/objects unmutated
