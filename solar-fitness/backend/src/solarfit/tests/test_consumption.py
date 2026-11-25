"""§16 Testing — engine/consumption.py, and the CON-05 wiring it feeds.

The point of this module is that a real household stops being told it can
fit 41 kWp. So alongside the conversion arithmetic, these tests check the
thing that actually matters: that a bill reaches
consumption_offset_ceiling and comes back as a believable system size,
and that no bill still degrades to insufficient_data rather than to a
guess.
"""

import pytest

from solarfit.engine.consumption import MONTHS_PER_YEAR, estimate_annual_consumption
from solarfit.packs import rooftop
from solarfit.packs.config_pack import (
    get_consumption_offset_assumed_yield,
    get_consumption_offset_target_ratio,
    get_electricity_tariff_inr_per_kwh,
)

TARIFF = 10.0  # explicit in most tests, so they don't move when the pack does


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


def test_bill_range_converts_to_annual_units():
    estimate = estimate_annual_consumption(1000, 2000, tariff_inr_per_kwh=TARIFF)

    assert estimate is not None
    # Midpoint 1500 INR/month at 10 INR/unit = 150 units/month.
    assert estimate.average_monthly_bill_inr == pytest.approx(1500.0)
    assert estimate.average_monthly_kwh == pytest.approx(150.0)
    assert estimate.annual_kwh == pytest.approx(150.0 * MONTHS_PER_YEAR)
    assert estimate.tariff_inr_per_kwh == TARIFF


def test_the_two_endpoints_are_averaged_not_maxed():
    """Sizing off the summer peak would oversize the system for most of
    the year; sizing off the winter trough would undersize it."""
    estimate = estimate_annual_consumption(1000, 5000, tariff_inr_per_kwh=TARIFF)

    assert estimate.average_monthly_bill_inr == pytest.approx(3000.0)
    assert estimate.average_monthly_bill_inr < 5000.0
    assert estimate.average_monthly_bill_inr > 1000.0


def test_a_reversed_range_is_swapped_not_discarded():
    """Almost certainly the two fields were filled the wrong way round —
    the midpoint is identical either way, so recovering is kinder than
    throwing the customer's input away."""
    forward = estimate_annual_consumption(1200, 3600, tariff_inr_per_kwh=TARIFF)
    reversed_ = estimate_annual_consumption(3600, 1200, tariff_inr_per_kwh=TARIFF)

    assert reversed_ is not None
    assert reversed_.annual_kwh == pytest.approx(forward.annual_kwh)


def test_equal_low_and_high_is_a_flat_bill_not_an_error():
    estimate = estimate_annual_consumption(2000, 2000, tariff_inr_per_kwh=TARIFF)

    assert estimate is not None
    assert estimate.average_monthly_kwh == pytest.approx(200.0)


def test_a_higher_tariff_implies_fewer_units_for_the_same_money():
    cheap = estimate_annual_consumption(3000, 3000, tariff_inr_per_kwh=5.0)
    dear = estimate_annual_consumption(3000, 3000, tariff_inr_per_kwh=10.0)

    assert cheap.annual_kwh == pytest.approx(dear.annual_kwh * 2)


def test_basis_states_its_provenance():
    """The figure is derived from an assumed tariff, not measured, so it
    has to be able to say so on screen."""
    basis = estimate_annual_consumption(1000, 2000, tariff_inr_per_kwh=TARIFF).basis

    assert "units/month" in basis
    assert "1,500" in basis  # the average bill it actually used
    assert "10" in basis  # the tariff it actually used


def test_the_pack_supplies_the_default_tariff():
    estimate = estimate_annual_consumption(1600, 1600)
    assert estimate.tariff_inr_per_kwh == get_electricity_tariff_inr_per_kwh()


# ---------------------------------------------------------------------------
# Absence — a missing or nonsensical bill must never become a guess
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("low", "high"),
    [(None, None), (None, 2000), (1000, None), (0, 2000), (1000, 0), (-500, 2000)],
)
def test_unusable_input_yields_no_estimate(low, high):
    assert estimate_annual_consumption(low, high) is None


def test_a_zero_tariff_is_refused_rather_than_dividing_by_zero():
    assert estimate_annual_consumption(1000, 2000, tariff_inr_per_kwh=0.0) is None


# ---------------------------------------------------------------------------
# CON-05 — the wiring this module exists to feed
# ---------------------------------------------------------------------------


def test_a_bill_produces_a_real_consumption_ceiling():
    estimate = estimate_annual_consumption(3000, 6000)
    ceiling = rooftop.consumption_offset_ceiling(
        None, {"annual_consumption_kwh": estimate.annual_kwh}
    )

    expected = (
        estimate.annual_kwh * get_consumption_offset_target_ratio()
    ) / get_consumption_offset_assumed_yield()
    assert ceiling.status == "ok"
    assert ceiling.ceiling_kwp == pytest.approx(expected)


def test_a_household_bill_sizes_a_household_system():
    """The regression this whole feature exists for: before a bill could
    be captured, an ordinary house was capped only by roof area and came
    back at tens of kWp it could never use."""
    estimate = estimate_annual_consumption(3000, 6000)
    ceiling = rooftop.consumption_offset_ceiling(
        None, {"annual_consumption_kwh": estimate.annual_kwh}
    )

    assert 1.0 < ceiling.ceiling_kwp < 15.0, "a domestic bill should not size an industrial array"


def test_a_larger_bill_permits_a_larger_system():
    small = estimate_annual_consumption(1000, 2000)
    large = estimate_annual_consumption(10000, 20000)

    small_ceiling = rooftop.consumption_offset_ceiling(
        None, {"annual_consumption_kwh": small.annual_kwh}
    )
    large_ceiling = rooftop.consumption_offset_ceiling(
        None, {"annual_consumption_kwh": large.annual_kwh}
    )

    assert large_ceiling.ceiling_kwp > small_ceiling.ceiling_kwp


def test_no_bill_leaves_con_05_reporting_insufficient_data():
    """Unchanged behaviour for every existing check: no bill means the
    ceiling abstains, it does not invent a consumption figure."""
    ceiling = rooftop.consumption_offset_ceiling(None, {})

    assert ceiling.status == "insufficient_data"
    assert ceiling.ceiling_kwp is None
