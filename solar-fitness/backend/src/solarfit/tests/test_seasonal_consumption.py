"""FIN-03 — engine/seasonal_consumption.py. A customer gives only their
highest and lowest month; every other figure here is derived from that
pair plus admin-configured season month-counts and a rainy-season
interpolation factor. Same plain-pytest, explicit-params, no-mocking
style as test_consumption.py.
"""

import pytest

from solarfit.engine.seasonal_consumption import estimate_seasonal_consumption

TARIFF = 8.0


def _estimate(**overrides):
    defaults = dict(
        highest_consumption_kwh=900.0,
        lowest_consumption_kwh=400.0,
        monthly_bill_high_inr=None,
        monthly_bill_low_inr=None,
        tariff_inr_per_kwh=TARIFF,
        rainy_factor_pct=50.0,
        summer_months=4,
        rainy_months=4,
        winter_months=4,
    )
    defaults.update(overrides)
    return estimate_seasonal_consumption(**defaults)


# ---------------------------------------------------------------------------
# The spec's own worked example
# ---------------------------------------------------------------------------


def test_the_spec_worked_example_matches_exactly():
    est = _estimate()

    assert est.seasons["summer"].monthly_kwh == 900
    assert est.seasons["summer"].annual_kwh == 3600
    assert est.seasons["rainy"].monthly_kwh == pytest.approx(650.0)
    assert est.seasons["rainy"].annual_kwh == pytest.approx(2600.0)
    assert est.seasons["winter"].monthly_kwh == 400
    assert est.seasons["winter"].annual_kwh == 1600
    assert est.annual_kwh == pytest.approx(7800.0)
    assert est.average_monthly_kwh == pytest.approx(650.0)


def test_rainy_is_flagged_estimated_summer_and_winter_are_not_when_kwh_given():
    est = _estimate()
    assert est.seasons["rainy"].estimated is True
    assert est.seasons["summer"].estimated is False
    assert est.seasons["winter"].estimated is False


def test_source_is_kwh_reading_when_kwh_given():
    assert _estimate().source == "kwh_reading"


# ---------------------------------------------------------------------------
# kWh is primary; ₹ is a fallback, never a mix
# ---------------------------------------------------------------------------


def test_bill_amount_fallback_when_no_kwh_given():
    est = _estimate(
        highest_consumption_kwh=None,
        lowest_consumption_kwh=None,
        monthly_bill_high_inr=7200.0,
        monthly_bill_low_inr=3200.0,
        tariff_inr_per_kwh=8.0,
    )
    assert est is not None
    assert est.source == "bill_amount_estimate"
    assert est.seasons["summer"].monthly_kwh == pytest.approx(900.0)
    assert est.seasons["winter"].monthly_kwh == pytest.approx(400.0)
    # A converted figure is this module's own estimate, not the customer's
    # reported reading — summer/winter are flagged estimated too here.
    assert est.seasons["summer"].estimated is True
    assert est.seasons["winter"].estimated is True


def test_a_partial_kwh_pair_is_treated_as_absent_not_mixed_with_the_bill():
    """Only a highest kWh given, no lowest — must not silently borrow the
    lowest from a ₹ conversion instead."""
    est = _estimate(
        highest_consumption_kwh=900.0,
        lowest_consumption_kwh=None,
        monthly_bill_high_inr=7200.0,
        monthly_bill_low_inr=3200.0,
    )
    assert est is not None
    assert est.source == "bill_amount_estimate"  # fell back to bill for BOTH, not a mix


def test_missing_both_kwh_and_bill_returns_none():
    assert _estimate(highest_consumption_kwh=None, lowest_consumption_kwh=None) is None


def test_zero_tariff_refuses_bill_fallback_rather_than_dividing_by_zero():
    est = _estimate(
        highest_consumption_kwh=None,
        lowest_consumption_kwh=None,
        monthly_bill_high_inr=7200.0,
        monthly_bill_low_inr=3200.0,
        tariff_inr_per_kwh=0.0,
    )
    assert est is None


# ---------------------------------------------------------------------------
# Validation — §31
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("high", "low"), [(0.0, 400.0), (900.0, 0.0), (-100.0, 400.0), (900.0, -50.0)]
)
def test_non_positive_consumption_is_rejected(high, low):
    assert _estimate(highest_consumption_kwh=high, lowest_consumption_kwh=low) is None


def test_a_reversed_high_low_pair_is_swapped_not_discarded():
    forward = _estimate(highest_consumption_kwh=900.0, lowest_consumption_kwh=400.0)
    reversed_ = _estimate(highest_consumption_kwh=400.0, lowest_consumption_kwh=900.0)
    assert reversed_.annual_kwh == pytest.approx(forward.annual_kwh)


def test_equal_high_and_low_is_a_flat_profile_not_an_error():
    est = _estimate(highest_consumption_kwh=500.0, lowest_consumption_kwh=500.0)
    assert est is not None
    assert est.seasons["summer"].monthly_kwh == est.seasons["rainy"].monthly_kwh == est.seasons["winter"].monthly_kwh == 500.0


# ---------------------------------------------------------------------------
# Admin-configurable knobs actually change the result
# ---------------------------------------------------------------------------


def test_a_different_rainy_factor_only_moves_the_rainy_season():
    low_factor = _estimate(rainy_factor_pct=25.0)
    high_factor = _estimate(rainy_factor_pct=75.0)

    assert low_factor.seasons["summer"].monthly_kwh == high_factor.seasons["summer"].monthly_kwh
    assert low_factor.seasons["winter"].monthly_kwh == high_factor.seasons["winter"].monthly_kwh
    assert low_factor.seasons["rainy"].monthly_kwh < high_factor.seasons["rainy"].monthly_kwh


def test_zero_rainy_factor_makes_rainy_equal_winter():
    est = _estimate(rainy_factor_pct=0.0)
    assert est.seasons["rainy"].monthly_kwh == pytest.approx(est.seasons["winter"].monthly_kwh)


def test_hundred_pct_rainy_factor_makes_rainy_equal_summer():
    est = _estimate(rainy_factor_pct=100.0)
    assert est.seasons["rainy"].monthly_kwh == pytest.approx(est.seasons["summer"].monthly_kwh)


def test_different_season_month_durations_change_the_annual_total():
    even = _estimate(summer_months=4, rainy_months=4, winter_months=4)
    summer_heavy = _estimate(summer_months=6, rainy_months=3, winter_months=3)
    # More months at the (higher) summer rate and fewer at the (lower)
    # winter rate must raise the annual total.
    assert summer_heavy.annual_kwh > even.annual_kwh


def test_average_monthly_kwh_divides_by_the_actual_configured_month_total():
    est = _estimate(summer_months=6, rainy_months=3, winter_months=3)
    assert est.average_monthly_kwh == pytest.approx(est.annual_kwh / 12)


# ---------------------------------------------------------------------------
# Transparency — §5/§28: never present the rainy estimate as a measurement
# ---------------------------------------------------------------------------


def test_basis_mentions_interpolation_and_the_factor_used():
    basis = _estimate(rainy_factor_pct=50.0).basis
    assert "interpolated" in basis.lower()
    assert "50%" in basis


def test_basis_distinguishes_kwh_reading_from_bill_estimate():
    kwh_basis = _estimate().basis
    bill_basis = _estimate(
        highest_consumption_kwh=None,
        lowest_consumption_kwh=None,
        monthly_bill_high_inr=7200.0,
        monthly_bill_low_inr=3200.0,
    ).basis
    assert "reported highest/lowest monthly usage" in kwh_basis
    assert "bill amount" in bill_basis
