"""FIN-03 — turns a customer's two-point electricity usage (their highest
and lowest month) into a 3-season, then annual, consumption estimate.

Why this exists: a customer can reasonably state their bill's peak and
trough but not 12 months of history. Every downstream figure (seasonal
generation match, seasonal/year-wise savings, electricity-based sizing)
needs a real annual kWh number, not a guess — this is the one place that
conversion happens, reused by every caller rather than re-derived.

kWh is PRIMARY. `highest_consumption_kwh`/`lowest_consumption_kwh` (real
units the customer read off their meter/bill) are preferred whenever
given; the ₹ bill-amount pair is only ever used to approximate the same
two kWh figures via a flat tariff when the customer doesn't know their
units — same "don't calculate solar sizing directly from a rupee amount"
discipline the spec requires. Never averages the two sources together —
one or the other, so the provenance stays honest and explainable.

The rainy/monsoon season is never a measurement — it's interpolated
between the customer's own two real data points using an admin-editable
factor, and every returned estimate says so via `.basis`/`seasons[...].
estimated`, so the UI can never present it as if it were reported.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SEASONS: tuple[str, ...] = ("summer", "rainy", "winter")


@dataclass(frozen=True)
class SeasonEstimate:
    monthly_kwh: float
    months: int
    annual_kwh: float
    # False only for summer/winter when they come straight from the
    # customer's own two real readings; rainy is always interpolated,
    # and summer/winter are too whenever the customer supplied a ₹
    # amount instead of a direct kWh reading (a converted figure is an
    # estimate of theirs, not a report of theirs).
    estimated: bool


@dataclass(frozen=True)
class SeasonalConsumptionEstimate:
    """What a customer's highest/lowest usage implies about their annual
    electricity consumption — the FIN-03 result every seasonal and
    year-wise view is built from."""

    seasons: dict[str, SeasonEstimate]
    annual_kwh: float
    average_monthly_kwh: float
    highest_monthly_kwh: float
    lowest_monthly_kwh: float
    source: str  # "kwh_reading" | "bill_amount_estimate"
    rainy_factor_pct: float

    @property
    def basis(self) -> str:
        """Plain-English provenance for showing beside the figures."""
        origin = (
            "your reported highest/lowest monthly usage"
            if self.source == "kwh_reading"
            else "your highest/lowest bill amount, converted at the configured tariff"
        )
        return (
            f"Estimated from {origin}. Rainy-season usage is interpolated "
            f"({self.rainy_factor_pct:g}% of the gap between your highest and lowest month) "
            "and is not a measured figure."
        )


def _season_estimate(monthly_kwh: float, months: int, *, estimated: bool) -> SeasonEstimate:
    return SeasonEstimate(
        monthly_kwh=monthly_kwh, months=months, annual_kwh=monthly_kwh * months, estimated=estimated
    )


def estimate_seasonal_consumption(
    *,
    highest_consumption_kwh: float | None,
    lowest_consumption_kwh: float | None,
    monthly_bill_high_inr: float | None = None,
    monthly_bill_low_inr: float | None = None,
    tariff_inr_per_kwh: float,
    rainy_factor_pct: float,
    summer_months: int,
    rainy_months: int,
    winter_months: int,
) -> SeasonalConsumptionEstimate | None:
    """FIN-03. Returns None when there is nothing usable to estimate from
    — never a guessed consumption figure standing in for real input.

    Prefers the direct kWh pair; falls back to converting the ₹ bill pair
    via `tariff_inr_per_kwh` only when a kWh reading is missing. Mixing
    (e.g. a kWh high + a ₹ low) is deliberately not supported — the two
    scales would need reconciling per-value, and a customer who read one
    meter figure almost always has the other too; treat a partial pair as
    absent rather than silently converting only half of it.
    """
    source = "kwh_reading"
    high, low = highest_consumption_kwh, lowest_consumption_kwh

    if high is None or low is None:
        if monthly_bill_high_inr is None or monthly_bill_low_inr is None:
            return None
        if tariff_inr_per_kwh <= 0:
            logger.error("Electricity tariff is not positive (%s) — cannot convert a bill", tariff_inr_per_kwh)
            return None
        if monthly_bill_high_inr <= 0 or monthly_bill_low_inr <= 0:
            return None
        high = monthly_bill_high_inr / tariff_inr_per_kwh
        low = monthly_bill_low_inr / tariff_inr_per_kwh
        source = "bill_amount_estimate"

    if high <= 0 or low <= 0:
        logger.info("Consumption rejected: non-positive (%s, %s)", low, high)
        return None
    if high < low:
        # Almost certainly the two fields were filled the wrong way round
        # — same "swap, don't discard" reasoning as engine/consumption.py.
        low, high = high, low

    rainy = low + (high - low) * (rainy_factor_pct / 100.0)
    kwh_is_estimated = source == "bill_amount_estimate"

    seasons = {
        "summer": _season_estimate(high, summer_months, estimated=kwh_is_estimated),
        "rainy": _season_estimate(rainy, rainy_months, estimated=True),
        "winter": _season_estimate(low, winter_months, estimated=kwh_is_estimated),
    }
    annual_kwh = sum(s.annual_kwh for s in seasons.values())
    total_months = summer_months + rainy_months + winter_months

    return SeasonalConsumptionEstimate(
        seasons=seasons,
        annual_kwh=annual_kwh,
        average_monthly_kwh=annual_kwh / total_months if total_months > 0 else 0.0,
        highest_monthly_kwh=high,
        lowest_monthly_kwh=low,
        source=source,
        rainy_factor_pct=rainy_factor_pct,
    )
