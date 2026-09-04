"""Turns a customer's electricity bill into the annual consumption figure
CON-05's consumption-offset ceiling needs.

Why this exists: packs/rooftop.py::consumption_offset_ceiling() has always
read params["annual_consumption_kwh"], and nothing has ever supplied it,
so on every assessment to date that ceiling has returned
"insufficient_data" and the recommended size has been capped by roof area
alone. That is why a suburban house comes back at 41 kWp — nothing was
telling the engine how much electricity the household actually uses.

Customers know what they PAY, not how many units they used, so the form
asks for a rupee range and this converts it. The tariff is a config-pack
placeholder average, not a slab model — see the pack's own note. Every
bill-derived system size scales inversely with it, so this module keeps
the conversion in one auditable place rather than scattering a division
through the routers.

A range rather than one figure because bills swing seasonally: an Indian
household's summer bill can be double its winter one, and either endpoint
alone would size the system wrong in an obvious direction.
"""

import logging
from dataclasses import dataclass

from solarfit.packs import config_pack

logger = logging.getLogger(__name__)

MONTHS_PER_YEAR = 12


@dataclass(frozen=True)
class ConsumptionEstimate:
    """What a bill range implies about a household's electricity use."""

    annual_kwh: float
    average_monthly_kwh: float
    average_monthly_bill_inr: float
    tariff_inr_per_kwh: float

    @property
    def basis(self) -> str:
        """Plain-English provenance, for showing beside the number rather
        than presenting it as a measurement."""
        return (
            f"about {self.average_monthly_kwh:,.0f} units/month "
            f"from an average bill of Rs {self.average_monthly_bill_inr:,.0f} "
            f"at Rs {self.tariff_inr_per_kwh:g}/unit"
        )


def estimate_annual_consumption(
    monthly_bill_low_inr: float | None,
    monthly_bill_high_inr: float | None,
    *,
    tariff_inr_per_kwh: float | None = None,
) -> ConsumptionEstimate | None:
    """Annual kWh implied by a lowest/highest monthly bill pair.

    Returns None when there is nothing usable to convert — no bill, a
    non-positive one, or a pair that cannot be a real range. The caller
    then leaves annual_consumption_kwh unset and CON-05 reports
    insufficient_data, exactly as it does today. Guessing a household's
    consumption would put a fabricated number under a real quote.

    The two endpoints are averaged: the midpoint of the seasonal swing is
    the honest estimator of a typical month. Taking the high bill alone
    would oversize the system for eleven months of the year, and the low
    bill would undersize it for the months that matter most.
    """
    if monthly_bill_low_inr is None or monthly_bill_high_inr is None:
        return None

    low, high = float(monthly_bill_low_inr), float(monthly_bill_high_inr)
    if low <= 0 or high <= 0:
        logger.info("Bill range rejected: non-positive (%s, %s)", low, high)
        return None
    if high < low:
        # Almost certainly the fields were filled the wrong way round;
        # swapping is kinder than discarding, and the midpoint is the same.
        low, high = high, low

    # `is None`, not `or`: 0.0 is falsy, so `or` would silently swap an
    # explicitly-passed zero for the pack default and divide by that
    # instead of refusing the call.
    tariff = (
        config_pack.get_electricity_tariff_inr_per_kwh()
        if tariff_inr_per_kwh is None
        else tariff_inr_per_kwh
    )
    if tariff <= 0:
        logger.error("Electricity tariff is not positive (%s) — cannot convert a bill", tariff)
        return None

    average_bill = (low + high) / 2.0
    monthly_kwh = average_bill / tariff
    return ConsumptionEstimate(
        annual_kwh=monthly_kwh * MONTHS_PER_YEAR,
        average_monthly_kwh=monthly_kwh,
        average_monthly_bill_inr=average_bill,
        tariff_inr_per_kwh=tariff,
    )
