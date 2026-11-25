"""FIN-03 — the season-wise companion to engine/financial_projection.py's
year-wise ROI engine. Same central assumptions store, same reused
pieces (compute_emi(), the config-pack tariff, the admin-editable
maintenance/export-rate figures) — this module adds no new financial
formula of its own beyond allocating them across three seasons instead
of 25 years, per the spec's own "do not implement separate formulas
independently" instruction (§29).

Generation seasonality prefers REAL data: when a real 12-month PVGIS
breakdown exists (engine/generation.py's `pvgis_monthly_kwh`), each
season's share of annual generation is measured from it via an
admin-configured calendar-month mapping. Only when that's unavailable
does it fall back to admin-configured flat shares — same "real data
opportunistically refines a configured default" pattern this codebase
already uses for weather-refined specific yield (GEN-02).
"""

from __future__ import annotations

from dataclasses import dataclass

from solarfit.engine.seasonal_consumption import SEASONS, SeasonalConsumptionEstimate
from solarfit.packs import config_pack

# Mirrors repositories/financial_config.py::DEFAULT_ASSUMPTIONS' own values
# for these same keys — this engine module deliberately doesn't import the
# repositories layer (engine stays agnostic of where `assumptions` came
# from, same separation financial_projection.py already keeps), so an
# admin row saved before these keys existed still degrades to the exact
# same fallback a fresh install seeds, read via `.get(key, _FALLBACK)`
# at each call site below rather than a bare `assumptions[key]`.
_DEFAULT_SEASON_CALENDAR_MONTHS = {"summer": [3, 4, 5, 6], "rainy": [7, 8, 9, 10], "winter": [11, 12, 1, 2]}


@dataclass(frozen=True)
class SeasonFinancial:
    season: str
    months: int
    consumption_kwh: float
    consumption_estimated: bool
    generation_kwh: float
    self_consumption_kwh: float
    export_kwh: float
    tariff_inr_per_kwh: float
    self_consumption_savings_inr: float
    export_revenue_inr: float
    gross_benefit_inr: float
    maintenance_cost_inr: float
    net_benefit_inr: float
    emi_cost_inr: float
    net_benefit_after_emi_inr: float


@dataclass(frozen=True)
class SeasonalFinancialResult:
    seasons: dict[str, SeasonFinancial]
    annual_generation_kwh: float
    annual_gross_benefit_inr: float
    annual_maintenance_inr: float
    annual_net_benefit_inr: float
    annual_emi_inr: float
    annual_net_benefit_after_emi_inr: float
    generation_shares: dict[str, float]
    generation_share_source: str  # "pvgis_actual" | "configured_fallback"


def seasonal_generation_shares(
    pvgis_monthly_kwh: list[float] | None,
    *,
    season_calendar_months: dict[str, list[int]],
    fallback_shares: dict[str, float],
) -> tuple[dict[str, float], str]:
    """Each season's fraction of annual generation (sums to 1.0).

    Prefers summing `pvgis_monthly_kwh`'s real Jan-Dec values into the
    admin-configured calendar-month buckets; falls back to the
    admin-configured flat shares when there's no real monthly breakdown
    (PVGIS was unavailable) or the mapping doesn't cover any real
    generation (defensive — never divide by zero silently into a
    fabricated even split without saying so).
    """
    if pvgis_monthly_kwh and len(pvgis_monthly_kwh) == 12:
        total = sum(pvgis_monthly_kwh)
        if total > 0:
            raw = {
                season: sum(
                    pvgis_monthly_kwh[month - 1] for month in months if 1 <= month <= 12
                )
                for season, months in season_calendar_months.items()
            }
            raw_total = sum(raw.values())
            if raw_total > 0:
                return {season: raw.get(season, 0.0) / raw_total for season in SEASONS}, "pvgis_actual"

    fallback_total = sum(fallback_shares.values())
    if fallback_total <= 0:
        return {season: 1.0 / len(SEASONS) for season in SEASONS}, "configured_fallback"
    return {season: fallback_shares.get(season, 0.0) / fallback_total for season in SEASONS}, "configured_fallback"


def project_seasonal_financials(
    *,
    capacity_kwp: float,
    annual_generation_kwh: float,
    pvgis_monthly_kwh: list[float] | None,
    consumption: SeasonalConsumptionEstimate,
    assumptions: dict,
    monthly_emi_inr: float = 0.0,
) -> SeasonalFinancialResult:
    """FIN-03. `monthly_emi_inr` is the SAME figure engine/
    financial_projection.py::compute_emi() already produces for the
    year-wise financing scenario — passed in, never recomputed here, so
    the seasonal and year-wise views can never quietly disagree about
    what the loan costs per month."""
    base_tariff = config_pack.get_electricity_tariff_inr_per_kwh()
    export_tariff = assumptions["export_tariff_inr_per_kwh"]
    annual_maintenance = assumptions["annual_maintenance_cost_inr_per_kwp"] * capacity_kwp

    shares, share_source = seasonal_generation_shares(
        pvgis_monthly_kwh,
        season_calendar_months=assumptions.get("season_calendar_months", _DEFAULT_SEASON_CALENDAR_MONTHS),
        fallback_shares={
            "summer": assumptions.get("summer_generation_share", 0.36),
            "rainy": assumptions.get("rainy_generation_share", 0.28),
            "winter": assumptions.get("winter_generation_share", 0.36),
        },
    )

    seasons: dict[str, SeasonFinancial] = {}
    for season in SEASONS:
        season_consumption = consumption.seasons[season]
        generation_kwh = annual_generation_kwh * shares[season]
        self_consumed = min(generation_kwh, season_consumption.annual_kwh)
        exported = max(0.0, generation_kwh - self_consumed)

        self_consumption_savings = self_consumed * base_tariff
        export_revenue = exported * export_tariff
        gross_benefit = self_consumption_savings + export_revenue

        maintenance_allocation = annual_maintenance * (season_consumption.months / 12.0)
        net_benefit = gross_benefit - maintenance_allocation

        emi_cost = monthly_emi_inr * season_consumption.months
        net_benefit_after_emi = net_benefit - emi_cost

        seasons[season] = SeasonFinancial(
            season=season,
            months=season_consumption.months,
            consumption_kwh=season_consumption.annual_kwh,
            consumption_estimated=season_consumption.estimated,
            generation_kwh=generation_kwh,
            self_consumption_kwh=self_consumed,
            export_kwh=exported,
            tariff_inr_per_kwh=base_tariff,
            self_consumption_savings_inr=self_consumption_savings,
            export_revenue_inr=export_revenue,
            gross_benefit_inr=gross_benefit,
            maintenance_cost_inr=maintenance_allocation,
            net_benefit_inr=net_benefit,
            emi_cost_inr=emi_cost,
            net_benefit_after_emi_inr=net_benefit_after_emi,
        )

    return SeasonalFinancialResult(
        seasons=seasons,
        annual_generation_kwh=sum(s.generation_kwh for s in seasons.values()),
        annual_gross_benefit_inr=sum(s.gross_benefit_inr for s in seasons.values()),
        annual_maintenance_inr=sum(s.maintenance_cost_inr for s in seasons.values()),
        annual_net_benefit_inr=sum(s.net_benefit_inr for s in seasons.values()),
        annual_emi_inr=sum(s.emi_cost_inr for s in seasons.values()),
        annual_net_benefit_after_emi_inr=sum(s.net_benefit_after_emi_inr for s in seasons.values()),
        generation_shares=shares,
        generation_share_source=share_source,
    )
