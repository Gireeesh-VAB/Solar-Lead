"""FIN-03 — engine/seasonal_financial_projection.py. Season-wise
generation/consumption/savings, reusing the same config-pack tariff and
the same EMI figure the year-wise engine already computes (never a
second EMI formula). Plain-pytest, explicit-params style.
"""

import pytest

from solarfit.engine.financial_projection import compute_emi
from solarfit.engine.seasonal_consumption import estimate_seasonal_consumption
from solarfit.engine.seasonal_financial_projection import (
    project_seasonal_financials,
    seasonal_generation_shares,
)
from solarfit.packs.config_pack import get_electricity_tariff_inr_per_kwh

ASSUMPTIONS = {
    "export_tariff_inr_per_kwh": 3.5,
    "annual_maintenance_cost_inr_per_kwp": 500.0,
    "summer_generation_share": 0.36,
    "rainy_generation_share": 0.28,
    "winter_generation_share": 0.36,
    "season_calendar_months": {"summer": [3, 4, 5, 6], "rainy": [7, 8, 9, 10], "winter": [11, 12, 1, 2]},
}


def _consumption(**overrides):
    defaults = dict(
        highest_consumption_kwh=900.0,
        lowest_consumption_kwh=400.0,
        tariff_inr_per_kwh=8.0,
        rainy_factor_pct=50.0,
        summer_months=4,
        rainy_months=4,
        winter_months=4,
    )
    defaults.update(overrides)
    return estimate_seasonal_consumption(**defaults)


# ---------------------------------------------------------------------------
# Generation shares
# ---------------------------------------------------------------------------


def test_shares_always_sum_to_one():
    shares, _source = seasonal_generation_shares(
        None,
        season_calendar_months=ASSUMPTIONS["season_calendar_months"],
        fallback_shares={"summer": 0.36, "rainy": 0.28, "winter": 0.36},
    )
    assert sum(shares.values()) == pytest.approx(1.0)


def test_falls_back_to_configured_shares_when_pvgis_unavailable():
    shares, source = seasonal_generation_shares(
        None,
        season_calendar_months=ASSUMPTIONS["season_calendar_months"],
        fallback_shares={"summer": 0.5, "rainy": 0.2, "winter": 0.3},
    )
    assert source == "configured_fallback"
    assert shares == {"summer": 0.5, "rainy": 0.2, "winter": 0.3}


def test_uses_real_pvgis_monthly_data_when_available():
    # A deliberately lopsided year: all real generation in Jan (winter
    # bucket) — the shares must reflect that, not the flat fallback.
    monthly = [1000.0] + [0.0] * 11
    shares, source = seasonal_generation_shares(
        monthly,
        season_calendar_months=ASSUMPTIONS["season_calendar_months"],
        fallback_shares={"summer": 0.36, "rainy": 0.28, "winter": 0.36},
    )
    assert source == "pvgis_actual"
    assert shares["winter"] == pytest.approx(1.0)
    assert shares["summer"] == pytest.approx(0.0)
    assert shares["rainy"] == pytest.approx(0.0)


def test_falls_back_when_pvgis_data_is_all_zero():
    shares, source = seasonal_generation_shares(
        [0.0] * 12,
        season_calendar_months=ASSUMPTIONS["season_calendar_months"],
        fallback_shares={"summer": 0.4, "rainy": 0.2, "winter": 0.4},
    )
    assert source == "configured_fallback"
    assert shares == {"summer": 0.4, "rainy": 0.2, "winter": 0.4}


def test_missing_calendar_months_still_normalizes_to_one():
    """A calendar mapping that only covers some months (a misconfigured
    admin entry) must not silently under-count — the real generation it
    DOES capture still normalizes to a full 1.0 across seasons."""
    monthly = [100.0] * 12
    shares, source = seasonal_generation_shares(
        monthly,
        season_calendar_months={"summer": [1, 2], "rainy": [3, 4], "winter": [5, 6]},  # only 6/12 months mapped
        fallback_shares={"summer": 0.36, "rainy": 0.28, "winter": 0.36},
    )
    assert source == "pvgis_actual"
    assert sum(shares.values()) == pytest.approx(1.0)
    # Equal real generation in every mapped month -> equal shares (2 months each).
    assert shares["summer"] == pytest.approx(shares["rainy"]) == pytest.approx(shares["winter"])


# ---------------------------------------------------------------------------
# Full seasonal financial projection
# ---------------------------------------------------------------------------


def test_worked_example_reconciles_with_annual_generation():
    consumption = _consumption()
    result = project_seasonal_financials(
        capacity_kwp=5.0,
        annual_generation_kwh=7000.0,
        pvgis_monthly_kwh=None,
        consumption=consumption,
        assumptions=ASSUMPTIONS,
    )
    # Season generation must sum back to the real annual figure — the
    # whole point of using shares instead of independent season formulas.
    assert result.annual_generation_kwh == pytest.approx(7000.0)
    assert sum(s.generation_kwh for s in result.seasons.values()) == pytest.approx(7000.0)


def test_self_consumption_is_capped_at_actual_seasonal_consumption():
    consumption = _consumption(highest_consumption_kwh=300.0, lowest_consumption_kwh=100.0)
    # A big system relative to this small household -> generation should
    # exceed consumption in the strong (summer) season, forcing export.
    result = project_seasonal_financials(
        capacity_kwp=10.0,
        annual_generation_kwh=14000.0,
        pvgis_monthly_kwh=None,
        consumption=consumption,
        assumptions=ASSUMPTIONS,
    )
    summer = result.seasons["summer"]
    assert summer.self_consumption_kwh == pytest.approx(summer.consumption_kwh)
    assert summer.export_kwh > 0


def test_export_revenue_uses_the_configured_export_rate_not_retail_tariff():
    consumption = _consumption(highest_consumption_kwh=200.0, lowest_consumption_kwh=50.0)
    result = project_seasonal_financials(
        capacity_kwp=10.0,
        annual_generation_kwh=14000.0,
        pvgis_monthly_kwh=None,
        consumption=consumption,
        assumptions=ASSUMPTIONS,
    )
    summer = result.seasons["summer"]
    assert summer.export_kwh > 0
    assert summer.export_revenue_inr == pytest.approx(summer.export_kwh * ASSUMPTIONS["export_tariff_inr_per_kwh"])


def test_maintenance_is_allocated_proportionally_to_season_months():
    consumption = _consumption(summer_months=6, rainy_months=3, winter_months=3)
    result = project_seasonal_financials(
        capacity_kwp=5.0, annual_generation_kwh=7000.0, pvgis_monthly_kwh=None,
        consumption=consumption, assumptions=ASSUMPTIONS,
    )
    annual_maintenance = ASSUMPTIONS["annual_maintenance_cost_inr_per_kwp"] * 5.0
    assert result.seasons["summer"].maintenance_cost_inr == pytest.approx(annual_maintenance * 6 / 12)
    assert result.seasons["rainy"].maintenance_cost_inr == pytest.approx(annual_maintenance * 3 / 12)
    assert result.annual_maintenance_inr == pytest.approx(annual_maintenance)


def test_emi_is_allocated_by_season_month_count_using_the_same_emi_figure():
    """§21 — Summer EMI = monthly EMI x summer months, etc. Reuses
    financial_projection.py's own compute_emi(), never a second formula."""
    consumption = _consumption(summer_months=5, rainy_months=4, winter_months=3)
    emi = compute_emi(200_000.0, 10.5, 5.0)
    result = project_seasonal_financials(
        capacity_kwp=5.0, annual_generation_kwh=7000.0, pvgis_monthly_kwh=None,
        consumption=consumption, assumptions=ASSUMPTIONS, monthly_emi_inr=emi.monthly_emi,
    )
    assert result.seasons["summer"].emi_cost_inr == pytest.approx(emi.monthly_emi * 5)
    assert result.seasons["rainy"].emi_cost_inr == pytest.approx(emi.monthly_emi * 4)
    assert result.seasons["winter"].emi_cost_inr == pytest.approx(emi.monthly_emi * 3)
    assert result.annual_emi_inr == pytest.approx(emi.monthly_emi * 12)
    assert result.annual_net_benefit_after_emi_inr == pytest.approx(
        result.annual_net_benefit_inr - result.annual_emi_inr
    )


def test_no_financing_means_zero_emi_and_net_benefit_after_emi_equals_net_benefit():
    consumption = _consumption()
    result = project_seasonal_financials(
        capacity_kwp=5.0, annual_generation_kwh=7000.0, pvgis_monthly_kwh=None,
        consumption=consumption, assumptions=ASSUMPTIONS,  # monthly_emi_inr defaults to 0.0
    )
    assert result.annual_emi_inr == 0.0
    assert result.annual_net_benefit_after_emi_inr == pytest.approx(result.annual_net_benefit_inr)


def test_tariff_used_matches_the_config_pack_not_a_hardcoded_value():
    consumption = _consumption()
    result = project_seasonal_financials(
        capacity_kwp=5.0, annual_generation_kwh=7000.0, pvgis_monthly_kwh=None,
        consumption=consumption, assumptions=ASSUMPTIONS,
    )
    for season in result.seasons.values():
        assert season.tariff_inr_per_kwh == get_electricity_tariff_inr_per_kwh()


def test_unknown_assumption_keys_fall_back_to_sensible_defaults():
    """An admin row saved before the seasonal-generation keys existed
    (missing summer_generation_share etc.) must not crash."""
    consumption = _consumption()
    old_row_assumptions = {
        "export_tariff_inr_per_kwh": 3.5,
        "annual_maintenance_cost_inr_per_kwp": 500.0,
    }
    result = project_seasonal_financials(
        capacity_kwp=5.0, annual_generation_kwh=7000.0, pvgis_monthly_kwh=None,
        consumption=consumption, assumptions=old_row_assumptions,
    )
    assert sum(s.generation_kwh for s in result.seasons.values()) == pytest.approx(7000.0)
