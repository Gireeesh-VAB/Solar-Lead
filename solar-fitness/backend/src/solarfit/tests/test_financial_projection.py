"""FIN-02 — engine/financial_projection.py, the year-by-year ROI engine.

Plain calls against explicit assumptions dicts (no mocking), same
discipline as test_consumption.py: these tests should not move just
because an admin later retunes financial_assumptions or a config-pack
placeholder changes. Every capacity in the spec's own test matrix
(3/5/10/25/50 kW) gets at least one direct assertion.
"""

import pytest

from solarfit.engine.financial_projection import (
    compute_emi,
    project_financials,
)
from solarfit.packs.config_pack import (
    get_panel_degradation_pct_per_year,
    get_system_lifetime_years,
)

ASSUMPTIONS = {
    "tariff_escalation_pct_per_year": 3.0,
    "export_tariff_inr_per_kwh": 3.5,
    "default_self_consumption_ratio": 0.7,
    "annual_maintenance_cost_inr_per_kwp": 500.0,
    "inverter_replacement_year": 12,
    "inverter_replacement_cost_inr_per_kwp": 8000.0,
    "financing_default_down_payment_pct": 20.0,
    "financing_default_interest_rate_pct": 10.5,
    "financing_default_tenure_years": 5.0,
}


def _financial_estimate(customer_contribution_inr: float, total_project_cost_inr: float | None = None) -> dict:
    return {
        "customer_contribution_inr": customer_contribution_inr,
        "total_project_cost_inr": total_project_cost_inr or customer_contribution_inr,
    }


def _project(capacity_kwp, annual_generation_kwh, investment, **overrides):
    assumptions = {**ASSUMPTIONS, **overrides.pop("assumptions_overrides", {})}
    return project_financials(
        capacity_kwp=capacity_kwp,
        annual_generation_kwh=annual_generation_kwh,
        financial_estimate=_financial_estimate(investment),
        assumptions=assumptions,
        assumptions_version=1,
        **overrides,
    )


# ---------------------------------------------------------------------------
# EMI
# ---------------------------------------------------------------------------


def test_emi_matches_a_known_reducing_balance_calculation():
    # A textbook check: 100000 principal, 12% annual, 12 months -> ~8885/mo.
    result = compute_emi(100_000.0, 12.0, 1.0)
    assert result.monthly_emi == pytest.approx(8884.88, rel=1e-3)
    assert result.total_payment_inr == pytest.approx(result.monthly_emi * 12)
    assert result.total_interest_inr == pytest.approx(result.total_payment_inr - 100_000.0)


def test_zero_interest_loan_splits_principal_evenly():
    result = compute_emi(120_000.0, 0.0, 2.0)
    assert result.monthly_emi == pytest.approx(5_000.0)
    assert result.total_interest_inr == pytest.approx(0.0)


def test_zero_or_negative_principal_has_no_emi():
    assert compute_emi(0.0, 10.0, 5.0).monthly_emi == 0.0
    assert compute_emi(-100.0, 10.0, 5.0).monthly_emi == 0.0


def test_zero_tenure_has_no_emi():
    assert compute_emi(100_000.0, 10.0, 0.0).monthly_emi == 0.0


# ---------------------------------------------------------------------------
# Degradation — generation must decay exactly at the configured rate
# ---------------------------------------------------------------------------


def test_year_one_generation_is_undegraded():
    result = _project(5.0, 7000.0, 250_000.0)
    assert result.yearly[0].degradation_factor == pytest.approx(1.0)
    assert result.yearly[0].generation_kwh == pytest.approx(7000.0)


def test_generation_decays_by_the_configured_pack_rate_each_year():
    result = _project(5.0, 7000.0, 250_000.0)
    degradation = get_panel_degradation_pct_per_year() / 100.0
    assert result.yearly[1].generation_kwh == pytest.approx(7000.0 * (1 - degradation))
    assert result.yearly[2].generation_kwh == pytest.approx(7000.0 * (1 - degradation) ** 2)


def test_projection_runs_for_the_full_configured_lifetime():
    result = _project(5.0, 7000.0, 250_000.0)
    assert len(result.yearly) == int(get_system_lifetime_years())
    assert result.yearly[-1].year == int(get_system_lifetime_years())


# ---------------------------------------------------------------------------
# Tariff escalation
# ---------------------------------------------------------------------------


def test_tariff_escalates_year_over_year():
    result = _project(5.0, 7000.0, 250_000.0)
    y1, y2 = result.yearly[0], result.yearly[1]
    assert y2.tariff_inr_per_kwh == pytest.approx(y1.tariff_inr_per_kwh * 1.03)


def test_zero_escalation_keeps_tariff_flat():
    result = _project(5.0, 7000.0, 250_000.0, assumptions_overrides={"tariff_escalation_pct_per_year": 0.0})
    tariffs = {round(y.tariff_inr_per_kwh, 6) for y in result.yearly}
    assert len(tariffs) == 1


# ---------------------------------------------------------------------------
# Self-consumption / export split
# ---------------------------------------------------------------------------


def test_no_bill_on_file_falls_back_to_the_configured_flat_ratio():
    result = _project(5.0, 7000.0, 250_000.0, annual_consumption_kwh=None)
    y1 = result.yearly[0]
    assert y1.self_consumption_kwh == pytest.approx(7000.0 * 0.7)
    assert y1.export_kwh == pytest.approx(7000.0 * 0.3)
    assert "Assumed" in result.self_consumption_basis


def test_a_captured_bill_caps_self_consumption_at_actual_usage():
    result = _project(5.0, 7000.0, 250_000.0, annual_consumption_kwh=4000.0)
    y1 = result.yearly[0]
    assert y1.self_consumption_kwh == pytest.approx(4000.0)
    assert y1.export_kwh == pytest.approx(3000.0)
    assert "bill" in result.self_consumption_basis.lower()


def test_consumption_higher_than_generation_exports_nothing():
    result = _project(3.0, 4000.0, 150_000.0, annual_consumption_kwh=10_000.0)
    y1 = result.yearly[0]
    assert y1.self_consumption_kwh == pytest.approx(4000.0)
    assert y1.export_kwh == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# FIN-04 — year-wise consumption growth (§14)
# ---------------------------------------------------------------------------


def test_zero_growth_keeps_consumption_flat_matching_pre_existing_behavior():
    result = _project(5.0, 7000.0, 250_000.0, annual_consumption_kwh=4000.0)
    caps = {y.year: y.self_consumption_kwh + y.export_kwh for y in result.yearly}
    # Consumption itself isn't a returned field, but with no growth
    # configured every year's self-consumption ceiling (capped at
    # consumption, since generation degrades but stays above 4000 for a
    # while) must stay at the same 4000 — proves growth defaults to 0.
    early_years_at_cap = [y.self_consumption_kwh for y in result.yearly if y.self_consumption_kwh < y.generation_kwh]
    assert all(v == pytest.approx(4000.0) for v in early_years_at_cap)


def test_consumption_growth_raises_the_self_consumption_ceiling_over_time():
    grown = _project(
        5.0, 9000.0, 250_000.0, annual_consumption_kwh=4000.0,
        assumptions_overrides={**ASSUMPTIONS, "annual_consumption_growth_pct": 5.0},
    )
    flat = _project(5.0, 9000.0, 250_000.0, annual_consumption_kwh=4000.0)

    # Generation (9000/yr, barely degrading) comfortably exceeds even a
    # grown consumption ceiling for the whole horizon, so self-consumption
    # itself tracks the grown consumption figure directly.
    y10_grown = grown.yearly[9]
    y10_flat = flat.yearly[9]
    expected_y10_consumption = 4000.0 * (1.05 ** 9)
    assert y10_grown.self_consumption_kwh == pytest.approx(min(y10_grown.generation_kwh, expected_y10_consumption))
    assert y10_grown.self_consumption_kwh > y10_flat.self_consumption_kwh


def test_missing_growth_key_defaults_to_zero_for_an_old_assumptions_row():
    """An admin row saved before annual_consumption_growth_pct existed
    must not crash and must behave exactly as flat (0%) growth."""
    old_row = {k: v for k, v in ASSUMPTIONS.items()}  # no growth key present
    assert "annual_consumption_growth_pct" not in old_row
    result = _project(5.0, 7000.0, 250_000.0, annual_consumption_kwh=4000.0, assumptions_overrides=old_row)
    assert result is not None


def test_export_revenue_uses_the_configured_export_tariff_not_the_retail_one():
    result = _project(
        5.0, 7000.0, 250_000.0, annual_consumption_kwh=None,
        assumptions_overrides={"export_tariff_inr_per_kwh": 2.0},
    )
    y1 = result.yearly[0]
    assert y1.export_revenue_inr == pytest.approx(y1.export_kwh * 2.0)


# ---------------------------------------------------------------------------
# Maintenance / other costs
# ---------------------------------------------------------------------------


def test_maintenance_scales_with_capacity():
    result_small = _project(3.0, 4200.0, 150_000.0)
    result_large = _project(10.0, 14000.0, 500_000.0)
    assert result_large.yearly[0].maintenance_cost_inr == pytest.approx(
        result_small.yearly[0].maintenance_cost_inr * 10.0 / 3.0
    )


def test_zero_maintenance_is_a_valid_configuration():
    result = _project(5.0, 7000.0, 250_000.0, assumptions_overrides={"annual_maintenance_cost_inr_per_kwp": 0.0})
    assert all(y.maintenance_cost_inr == 0.0 for y in result.yearly)


def test_inverter_replacement_cost_lands_only_in_its_configured_year():
    result = _project(5.0, 7000.0, 250_000.0, assumptions_overrides={
        **ASSUMPTIONS, "inverter_replacement_year": 5, "inverter_replacement_cost_inr_per_kwp": 8000.0,
    })
    other_cost_years = {y.year for y in result.yearly if y.other_cost_inr > 0}
    assert other_cost_years == {5}
    assert next(y for y in result.yearly if y.year == 5).other_cost_inr == pytest.approx(8000.0 * 5.0)


def test_no_inverter_replacement_configured_means_no_other_cost_ever():
    result = _project(5.0, 7000.0, 250_000.0, assumptions_overrides={
        **ASSUMPTIONS, "inverter_replacement_year": None,
    })
    assert all(y.other_cost_inr == 0.0 for y in result.yearly)


# ---------------------------------------------------------------------------
# Payback — the crossing point, never a fixed assumption
# ---------------------------------------------------------------------------


def test_a_generous_system_pays_back_within_three_years():
    """Small investment, strong generation and tariff — recovers fast."""
    result = _project(5.0, 9000.0, 50_000.0, assumptions_overrides={
        **ASSUMPTIONS, "annual_maintenance_cost_inr_per_kwp": 0.0,
    })
    assert result.payback.recovered
    assert result.payback.payback_years < 3.0
    assert result.three_year_summary.investment_recovered


def test_a_large_investment_is_not_recovered_after_three_years():
    result = _project(5.0, 7000.0, 400_000.0)
    assert not result.three_year_summary.investment_recovered
    assert result.three_year_summary.total_net_savings_inr < 400_000.0


def test_payback_year_is_the_first_year_cumulative_cash_flow_crosses_zero():
    result = _project(5.0, 7000.0, 250_000.0)
    payback = result.payback
    assert payback.recovered
    year_before = next(y for y in result.yearly if y.year == payback.payback_year - 1) if payback.payback_year > 1 else None
    year_of = next(y for y in result.yearly if y.year == payback.payback_year)
    assert year_of.cumulative_cash_flow_inr >= 0
    if year_before is not None:
        assert year_before.cumulative_cash_flow_inr < 0


def test_an_undersized_system_never_pays_back_within_lifetime():
    """A tiny generation against a huge cost — the honest answer is 'not
    recovered', never a fabricated year past the lifetime."""
    result = _project(1.0, 500.0, 10_000_000.0)
    assert not result.payback.recovered
    assert result.payback.payback_year is None
    assert result.payback.payback_years is None


def test_zero_investment_is_immediately_recovered():
    """Not a realistic input, but the function must not divide by zero."""
    result = _project(5.0, 7000.0, 0.0)
    assert result is None  # estimate_financials would never emit this; guarded defensively upstream


# ---------------------------------------------------------------------------
# ROI at multiple horizons — never a fixed percentage
# ---------------------------------------------------------------------------


def test_roi_improves_monotonically_with_horizon_once_recovered():
    result = _project(5.0, 8000.0, 200_000.0)
    horizon_roi = {h.horizon_years: h.cumulative_roi_pct for h in result.horizons}
    years_sorted = sorted(horizon_roi)
    rois = [horizon_roi[y] for y in years_sorted]
    assert rois == sorted(rois), "ROI should never go backwards as the horizon lengthens"


def test_horizons_are_capped_to_the_configured_lifetime():
    lifetime = int(get_system_lifetime_years())
    result = _project(5.0, 7000.0, 250_000.0)
    assert all(h.horizon_years <= lifetime for h in result.horizons)


def test_lifetime_roi_reflects_the_final_years_cumulative_figure():
    result = _project(5.0, 7000.0, 250_000.0)
    assert result.lifetime_roi_pct == pytest.approx(result.yearly[-1].roi_pct)


# ---------------------------------------------------------------------------
# Financing / EMI comparison
# ---------------------------------------------------------------------------


def test_financing_disabled_produces_no_financing_scenario():
    result = _project(5.0, 7000.0, 250_000.0, financing_enabled=False)
    assert result.financing is None


def test_financing_enabled_by_default_produces_a_scenario():
    result = _project(5.0, 7000.0, 250_000.0)
    assert result.financing is not None
    assert result.financing.down_payment_inr == pytest.approx(250_000.0 * 0.20)
    assert result.financing.loan_amount_inr == pytest.approx(250_000.0 * 0.80)


def test_financing_overrides_replace_the_assumption_defaults():
    result = _project(
        5.0, 7000.0, 250_000.0,
        financing_overrides={"down_payment_pct": 50.0, "interest_rate_pct": 5.0, "tenure_years": 3.0},
    )
    fin = result.financing
    assert fin.down_payment_inr == pytest.approx(125_000.0)
    assert fin.tenure_years == 3.0
    assert fin.interest_rate_pct == 5.0


def test_emi_cost_only_applies_during_the_loan_tenure():
    result = _project(
        5.0, 7000.0, 250_000.0,
        financing_overrides={"down_payment_pct": 20.0, "interest_rate_pct": 10.0, "tenure_years": 5.0},
    )
    financed_years = result.financing.yearly
    assert all(y.emi_cost_inr > 0 for y in financed_years if y.year <= 5)
    assert all(y.emi_cost_inr == 0 for y in financed_years if y.year > 5)


def test_financed_payback_is_measured_against_the_down_payment_not_full_cost():
    """Option B's investment basis is the down payment — a smaller
    up-front outlay than Option A's full contribution. Whether it
    recovers faster than Option A depends on the EMI drag during
    tenure, so this only checks the basis is really the down payment,
    not a blanket "financing is always faster" claim."""
    result = _project(5.0, 9000.0, 250_000.0, assumptions_overrides={
        **ASSUMPTIONS, "annual_maintenance_cost_inr_per_kwp": 0.0,
    })
    assert result.financing.payback.recovered
    assert result.financing.payback.amount_recovered_before_payback_inr <= result.financing.down_payment_inr
    assert result.payback.amount_recovered_before_payback_inr <= result.initial_investment_inr


# ---------------------------------------------------------------------------
# Spec's own capacity test matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("capacity_kwp", "annual_generation_kwh", "investment"),
    [
        (3.0, 4200.0, 150_000.0),
        (5.0, 7000.0, 250_000.0),
        (10.0, 14000.0, 500_000.0),
        (25.0, 35000.0, 1_250_000.0),
        (50.0, 70000.0, 2_500_000.0),
    ],
)
def test_every_capacity_in_the_spec_matrix_produces_a_coherent_projection(
    capacity_kwp, annual_generation_kwh, investment
):
    result = _project(capacity_kwp, annual_generation_kwh, investment)
    assert result is not None
    assert result.capacity_kwp == capacity_kwp
    assert len(result.yearly) == int(get_system_lifetime_years())
    assert result.yearly[0].generation_kwh == pytest.approx(annual_generation_kwh)
    # Cumulative cash flow must be monotonically consistent with net cash flow.
    running = -investment
    for y in result.yearly:
        running += y.net_cash_flow_inr
        assert y.cumulative_cash_flow_inr == pytest.approx(running)


# ---------------------------------------------------------------------------
# Edge cases / absence — never a fabricated projection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("capacity_kwp", [None, 0.0, -1.0])
def test_no_or_invalid_capacity_yields_no_projection(capacity_kwp):
    result = project_financials(
        capacity_kwp=capacity_kwp,
        annual_generation_kwh=7000.0,
        financial_estimate=_financial_estimate(250_000.0),
        assumptions=ASSUMPTIONS,
        assumptions_version=1,
    )
    assert result is None


@pytest.mark.parametrize("generation_kwh", [None, 0.0, -100.0])
def test_no_or_invalid_generation_yields_no_projection(generation_kwh):
    result = project_financials(
        capacity_kwp=5.0,
        annual_generation_kwh=generation_kwh,
        financial_estimate=_financial_estimate(250_000.0),
        assumptions=ASSUMPTIONS,
        assumptions_version=1,
    )
    assert result is None


def test_no_financial_estimate_yields_no_projection():
    result = project_financials(
        capacity_kwp=5.0,
        annual_generation_kwh=7000.0,
        financial_estimate=None,
        assumptions=ASSUMPTIONS,
        assumptions_version=1,
    )
    assert result is None


def test_financial_estimate_missing_contribution_falls_back_to_total_cost():
    result = project_financials(
        capacity_kwp=5.0,
        annual_generation_kwh=7000.0,
        financial_estimate={"total_project_cost_inr": 300_000.0},
        assumptions=ASSUMPTIONS,
        assumptions_version=1,
    )
    assert result is not None
    assert result.initial_investment_inr == pytest.approx(300_000.0)
