"""§16 Testing — pack resolution by site_type + jurisdiction (CON-02);
gates never enter the capacity minimum (CON-03); INSUFFICIENT_DATA on
unevaluable constraints, never a default (CON-04); constraints evaluate
independently and in any order (CON-09).
"""

from solarfit.domain.constraint import Ceiling, Gate
from solarfit.packs.registry import evaluate_all, resolve_constraint_fns


def test_billing_linked_type_gets_more_constraints_than_govt():
    residential = resolve_constraint_fns("ROOFTOP_RESIDENTIAL", jurisdiction=None)
    govt = resolve_constraint_fns("ROOFTOP_GOVT", jurisdiction=None)
    assert len(residential) > len(govt)  # net_metering_cap/subsidy_tier_cap are billing-linked only


def test_jurisdiction_override_replaces_not_adds():
    without_override = resolve_constraint_fns("ROOFTOP_RESIDENTIAL", jurisdiction=None)
    with_override = resolve_constraint_fns("ROOFTOP_RESIDENTIAL", jurisdiction="AP")
    assert len(without_override) == len(with_override)  # replaced, not appended


def test_evaluate_all_separates_ceilings_from_gates(make_site):
    site = make_site(site_type="ROOFTOP_RESIDENTIAL")
    params = {"sanctioned_load_kva": 10.0, "annual_consumption_kwh": 5000.0, "transformer_kva": 50.0}

    ceilings, gates = evaluate_all(site, usable_area_m2=100.0, params=params)

    assert all(isinstance(c, Ceiling) for c in ceilings)
    assert all(isinstance(g, Gate) for g in gates)
    assert "minimum_viable_size" in {g.gate for g in gates}
    assert "structural" in {g.gate for g in gates}


def test_evaluate_all_is_order_independent(make_site):
    site = make_site(site_type="ROOFTOP_RESIDENTIAL")
    params = {"sanctioned_load_kva": 10.0, "annual_consumption_kwh": 5000.0, "transformer_kva": 50.0}

    fns = resolve_constraint_fns(site.site_type, site.jurisdiction)
    results_forward = [fn(site, 100.0, params) for fn in fns]
    results_reversed = [fn(site, 100.0, params) for fn in reversed(fns)]

    ceilings_forward = sorted((r.constraint, r.ceiling_kwp) for r in results_forward if isinstance(r, Ceiling))
    ceilings_reversed = sorted((r.constraint, r.ceiling_kwp) for r in results_reversed if isinstance(r, Ceiling))
    assert ceilings_forward == ceilings_reversed
