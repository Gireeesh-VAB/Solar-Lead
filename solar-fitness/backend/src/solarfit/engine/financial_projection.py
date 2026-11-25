"""FIN-02 — the year-by-year Solar Financial Analysis / ROI engine.

Distinct from, and additive to, engine/financials.py's FIN-01 estimate:
FIN-01 already computes the cost breakdown, subsidy, and net customer
investment from the config-pack's installation_cost_inr_per_kwp/
subsidy_scheme — this module takes THAT output (never recomputes it,
per "do not create duplicate calculations") plus the capacity/generation
numbers already resolved upstream, and projects them forward year by
year with tariff escalation, panel degradation, a self-consumption/
export split, maintenance, an optional inverter replacement, and an
optional financed-purchase comparison.

Every new assumption this module needs beyond FIN-01's own (escalation
rate, export tariff, self-consumption default, maintenance, financing
defaults) comes from repositories/financial_config.py's DB-backed,
versioned, admin-editable FinancialAssumptionsRow — never hardcoded
here, so an admin can retune these without a deploy (CFG-01's spirit,
extended to a live-editable store for exactly the values that need one).
Panel degradation and system lifetime are deliberately NOT duplicated
into that store: they stay sourced from config_pack (the same values
FIN-01 already uses for its own 10/20-year figures), so the two engines
can never quietly disagree about how a panel degrades.

No fabrication: every total below is a mechanical function of its
inputs. A None generation/capacity produces a None projection, not a
guess. A financing scenario is only computed when financing is enabled
by the assumptions/request — never forced onto a customer who wants a
straight upfront-purchase view (see spec's "do not force financing").
"""

from __future__ import annotations

from dataclasses import dataclass

from solarfit.packs import config_pack

# Horizons the "long-term view" (spec §17) and lifetime-ROI table always
# report, capped to whatever the configured system lifetime actually
# covers (see _capped_horizons below) — never fabricated beyond it.
_STANDARD_HORIZONS_YEARS = (3, 5, 10, 15, 20, 25)


@dataclass(frozen=True)
class EmiResult:
    """Standard reducing-balance EMI — principal, monthly rate compounding,
    fixed monthly instalment. `monthly_emi` is 0.0 when there is no loan
    (principal <= 0), not a division-by-zero guess."""

    monthly_emi: float
    total_interest_inr: float
    total_payment_inr: float


def compute_emi(principal_inr: float, annual_interest_rate_pct: float, tenure_years: float) -> EmiResult:
    """Textbook EMI formula: EMI = P * r * (1+r)^n / ((1+r)^n - 1), r = monthly rate.

    A zero-interest loan (rate == 0) falls back to a plain principal/n
    split rather than dividing by zero in the compounding formula."""
    months = round(tenure_years * 12)
    if principal_inr <= 0 or months <= 0:
        return EmiResult(monthly_emi=0.0, total_interest_inr=0.0, total_payment_inr=0.0)

    monthly_rate = (annual_interest_rate_pct / 100.0) / 12.0
    if monthly_rate <= 0:
        emi = principal_inr / months
    else:
        factor = (1 + monthly_rate) ** months
        emi = principal_inr * monthly_rate * factor / (factor - 1)

    total_payment = emi * months
    return EmiResult(
        monthly_emi=emi,
        total_interest_inr=total_payment - principal_inr,
        total_payment_inr=total_payment,
    )


@dataclass(frozen=True)
class YearProjection:
    year: int
    generation_kwh: float
    degradation_factor: float
    tariff_inr_per_kwh: float
    self_consumption_kwh: float
    export_kwh: float
    self_consumption_savings_inr: float
    export_revenue_inr: float
    gross_benefit_inr: float
    maintenance_cost_inr: float
    other_cost_inr: float
    net_benefit_inr: float
    emi_cost_inr: float
    net_cash_flow_inr: float
    cumulative_savings_inr: float
    cumulative_cash_flow_inr: float
    remaining_investment_inr: float
    roi_pct: float


@dataclass(frozen=True)
class HorizonSummary:
    """Spec §9/§17 — "what happens after N years", one row per standard
    horizon (or the full lifetime, whichever is shorter)."""

    horizon_years: int
    total_generation_kwh: float
    total_gross_savings_inr: float
    total_costs_inr: float
    total_net_savings_inr: float
    cumulative_roi_pct: float
    investment_recovered: bool
    profit_after_recovery_inr: float


@dataclass(frozen=True)
class PaybackResult:
    """None fields mean the investment is not recovered within the
    configured system lifetime — a real, honest outcome for a
    marginal/oversized system, never silently clamped to the last year."""

    recovered: bool
    payback_year: int | None
    payback_years: float | None
    payback_months: int | None
    amount_recovered_before_payback_inr: float


@dataclass(frozen=True)
class FinancingScenario:
    down_payment_inr: float
    loan_amount_inr: float
    interest_rate_pct: float
    tenure_years: float
    monthly_emi_inr: float
    total_interest_inr: float
    total_payment_inr: float
    yearly: list[YearProjection]
    payback: PaybackResult
    horizons: list[HorizonSummary]


@dataclass(frozen=True)
class FinancialProjectionResult:
    capacity_kwp: float
    initial_investment_inr: float
    system_lifetime_years: int
    degradation_pct_per_year: float
    tariff_escalation_pct_per_year: float
    self_consumption_ratio_year1: float
    self_consumption_basis: str
    yearly: list[YearProjection]
    three_year_summary: HorizonSummary
    horizons: list[HorizonSummary]
    payback: PaybackResult
    lifetime_roi_pct: float
    financing: FinancingScenario | None
    method_notes: str
    assumptions_version: int


def _capped_horizons(lifetime_years: int) -> list[int]:
    return [h for h in _STANDARD_HORIZONS_YEARS if h <= lifetime_years]


def _project_years(
    *,
    capacity_kwp: float,
    annual_generation_kwh: float,
    initial_investment_inr: float,
    lifetime_years: int,
    degradation: float,
    base_tariff_inr_per_kwh: float,
    escalation: float,
    export_tariff_inr_per_kwh: float,
    self_consumption_ratio: float,
    annual_consumption_kwh: float | None,
    maintenance_inr_per_kwp_per_year: float,
    consumption_growth: float = 0.0,
    inverter_replacement_year: int | None,
    inverter_replacement_cost_inr: float,
    emi_monthly: float,
    emi_tenure_years: float,
    upfront_amount_inr: float,
) -> list[YearProjection]:
    """Shared per-year loop for both the upfront and financed scenarios —
    they differ only in `upfront_amount_inr` (the amount whose recovery
    cumulative_cash_flow_inr tracks) and `emi_monthly`/`emi_tenure_years`
    (zero/0 for the upfront scenario)."""
    years: list[YearProjection] = []
    cumulative_savings = 0.0
    cumulative_cash_flow = -upfront_amount_inr
    annual_maintenance = maintenance_inr_per_kwp_per_year * capacity_kwp
    emi_annual = emi_monthly * 12.0

    for year in range(1, lifetime_years + 1):
        degradation_factor = (1 - degradation) ** (year - 1)
        generation = annual_generation_kwh * degradation_factor
        tariff = base_tariff_inr_per_kwh * ((1 + escalation) ** (year - 1))

        if annual_consumption_kwh is not None:
            # FIN-04 — a household's usage grows too, not just the
            # tariff; a flat consumption figure held for 25 years would
            # overstate the export share (and understate savings) in
            # every later year once growth is configured.
            consumption_year_n = annual_consumption_kwh * ((1 + consumption_growth) ** (year - 1))
            self_consumed = min(generation, consumption_year_n)
        else:
            self_consumed = generation * self_consumption_ratio
        exported = max(0.0, generation - self_consumed)

        self_consumption_savings = self_consumed * tariff
        export_revenue = exported * export_tariff_inr_per_kwh
        gross_benefit = self_consumption_savings + export_revenue

        other_cost = (
            inverter_replacement_cost_inr
            if inverter_replacement_year is not None and year == inverter_replacement_year
            else 0.0
        )
        net_benefit = gross_benefit - annual_maintenance - other_cost

        emi_cost = emi_annual if year <= emi_tenure_years else 0.0
        net_cash_flow = net_benefit - emi_cost

        cumulative_savings += net_benefit
        cumulative_cash_flow += net_cash_flow
        remaining_investment = max(0.0, upfront_amount_inr - cumulative_savings)
        roi_pct = (
            ((cumulative_savings - upfront_amount_inr) / upfront_amount_inr) * 100.0
            if upfront_amount_inr > 0
            else 0.0
        )

        years.append(
            YearProjection(
                year=year,
                generation_kwh=generation,
                degradation_factor=degradation_factor,
                tariff_inr_per_kwh=tariff,
                self_consumption_kwh=self_consumed,
                export_kwh=exported,
                self_consumption_savings_inr=self_consumption_savings,
                export_revenue_inr=export_revenue,
                gross_benefit_inr=gross_benefit,
                maintenance_cost_inr=annual_maintenance,
                other_cost_inr=other_cost,
                net_benefit_inr=net_benefit,
                emi_cost_inr=emi_cost,
                net_cash_flow_inr=net_cash_flow,
                cumulative_savings_inr=cumulative_savings,
                cumulative_cash_flow_inr=cumulative_cash_flow,
                remaining_investment_inr=remaining_investment,
                roi_pct=roi_pct,
            )
        )
    return years


def _payback_from(years: list[YearProjection], upfront_amount_inr: float) -> PaybackResult:
    if upfront_amount_inr <= 0:
        return PaybackResult(
            recovered=True, payback_year=0, payback_years=0.0, payback_months=0,
            amount_recovered_before_payback_inr=0.0,
        )

    prev_cumulative = -upfront_amount_inr
    for y in years:
        if y.cumulative_cash_flow_inr >= 0:
            # Linear interpolation within the crossing year for a
            # fractional payback figure rather than only whole years.
            fraction = (
                abs(prev_cumulative) / y.net_cash_flow_inr if y.net_cash_flow_inr > 0 else 1.0
            )
            fraction = min(1.0, max(0.0, fraction))
            payback_years = (y.year - 1) + fraction
            return PaybackResult(
                recovered=True,
                payback_year=y.year,
                payback_years=payback_years,
                payback_months=round(payback_years * 12),
                amount_recovered_before_payback_inr=upfront_amount_inr + prev_cumulative,
            )
        prev_cumulative = y.cumulative_cash_flow_inr

    return PaybackResult(
        recovered=False, payback_year=None, payback_years=None, payback_months=None,
        amount_recovered_before_payback_inr=years[-1].cumulative_savings_inr if years else 0.0,
    )


def _horizon_summary(years: list[YearProjection], horizon_years: int, upfront_amount_inr: float) -> HorizonSummary:
    window = [y for y in years if y.year <= horizon_years]
    total_generation = sum(y.generation_kwh for y in window)
    total_gross_savings = sum(y.gross_benefit_inr for y in window)
    total_costs = sum(y.maintenance_cost_inr + y.other_cost_inr for y in window)
    total_net_savings = sum(y.net_benefit_inr for y in window)
    cumulative_roi = window[-1].roi_pct if window else 0.0
    recovered = total_net_savings >= upfront_amount_inr if upfront_amount_inr > 0 else True
    profit_after_recovery = max(0.0, total_net_savings - upfront_amount_inr)
    return HorizonSummary(
        horizon_years=horizon_years,
        total_generation_kwh=total_generation,
        total_gross_savings_inr=total_gross_savings,
        total_costs_inr=total_costs,
        total_net_savings_inr=total_net_savings,
        cumulative_roi_pct=cumulative_roi,
        investment_recovered=recovered,
        profit_after_recovery_inr=profit_after_recovery,
    )


def project_financials(
    *,
    capacity_kwp: float | None,
    annual_generation_kwh: float | None,
    financial_estimate: dict | None,
    assumptions: dict,
    assumptions_version: int,
    annual_consumption_kwh: float | None = None,
    financing_enabled: bool = True,
    financing_overrides: dict | None = None,
) -> FinancialProjectionResult | None:
    """The one entry point routers/app_financials.py calls.

    Returns None when there is nothing to project — no resolved
    capacity/generation, or FIN-01 itself produced no cost estimate
    (capacity_kwp <= 0). Mirrors engine/financials.py::estimate_financials()'s
    own "None, not a guess" discipline.
    """
    if not capacity_kwp or capacity_kwp <= 0:
        return None
    if not annual_generation_kwh or annual_generation_kwh <= 0:
        return None
    if not financial_estimate:
        return None

    initial_investment = financial_estimate.get("customer_contribution_inr")
    if initial_investment is None:
        initial_investment = financial_estimate.get("total_project_cost_inr")
    if initial_investment is None or initial_investment <= 0:
        return None

    base_tariff = config_pack.get_electricity_tariff_inr_per_kwh()
    degradation = config_pack.get_panel_degradation_pct_per_year() / 100.0
    lifetime_years = int(config_pack.get_system_lifetime_years())

    escalation = assumptions["tariff_escalation_pct_per_year"] / 100.0
    # FIN-04 — optional, defaults to 0 (flat) so an assumptions row saved
    # before this key existed behaves exactly as it did before.
    consumption_growth = assumptions.get("annual_consumption_growth_pct", 0.0) / 100.0
    export_tariff = assumptions["export_tariff_inr_per_kwh"]
    self_consumption_ratio = assumptions["default_self_consumption_ratio"]
    maintenance_per_kwp = assumptions["annual_maintenance_cost_inr_per_kwp"]
    inverter_year = assumptions.get("inverter_replacement_year")
    inverter_cost_per_kwp = assumptions.get("inverter_replacement_cost_inr_per_kwp") or 0.0
    inverter_cost = inverter_cost_per_kwp * capacity_kwp if inverter_year else 0.0

    self_consumption_basis = (
        "Based on your own captured bill range"
        if annual_consumption_kwh is not None
        else f"Assumed {self_consumption_ratio:.0%} self-consumption (no bill on file)"
    )

    upfront_years = _project_years(
        capacity_kwp=capacity_kwp,
        annual_generation_kwh=annual_generation_kwh,
        initial_investment_inr=initial_investment,
        lifetime_years=lifetime_years,
        degradation=degradation,
        base_tariff_inr_per_kwh=base_tariff,
        escalation=escalation,
        export_tariff_inr_per_kwh=export_tariff,
        self_consumption_ratio=self_consumption_ratio,
        annual_consumption_kwh=annual_consumption_kwh,
        consumption_growth=consumption_growth,
        maintenance_inr_per_kwp_per_year=maintenance_per_kwp,
        inverter_replacement_year=inverter_year,
        inverter_replacement_cost_inr=inverter_cost,
        emi_monthly=0.0,
        emi_tenure_years=0.0,
        upfront_amount_inr=initial_investment,
    )
    payback = _payback_from(upfront_years, initial_investment)
    horizons = [_horizon_summary(upfront_years, h, initial_investment) for h in _capped_horizons(lifetime_years)]
    three_year_summary = _horizon_summary(upfront_years, min(3, lifetime_years), initial_investment)
    lifetime_roi = upfront_years[-1].roi_pct if upfront_years else 0.0

    financing_scenario: FinancingScenario | None = None
    if financing_enabled:
        overrides = financing_overrides or {}
        down_payment_pct = overrides.get("down_payment_pct", assumptions["financing_default_down_payment_pct"])
        interest_rate_pct = overrides.get("interest_rate_pct", assumptions["financing_default_interest_rate_pct"])
        tenure_years = overrides.get("tenure_years", assumptions["financing_default_tenure_years"])

        down_payment_inr = initial_investment * (down_payment_pct / 100.0)
        loan_amount = max(0.0, initial_investment - down_payment_inr)
        emi = compute_emi(loan_amount, interest_rate_pct, tenure_years)

        financed_years = _project_years(
            capacity_kwp=capacity_kwp,
            annual_generation_kwh=annual_generation_kwh,
            initial_investment_inr=initial_investment,
            lifetime_years=lifetime_years,
            degradation=degradation,
            base_tariff_inr_per_kwh=base_tariff,
            escalation=escalation,
            export_tariff_inr_per_kwh=export_tariff,
            self_consumption_ratio=self_consumption_ratio,
            annual_consumption_kwh=annual_consumption_kwh,
            maintenance_inr_per_kwp_per_year=maintenance_per_kwp,
            inverter_replacement_year=inverter_year,
            inverter_replacement_cost_inr=inverter_cost,
            emi_monthly=emi.monthly_emi,
            emi_tenure_years=tenure_years,
            upfront_amount_inr=down_payment_inr,
        )
        financed_payback = _payback_from(financed_years, down_payment_inr)
        financed_horizons = [
            _horizon_summary(financed_years, h, down_payment_inr) for h in _capped_horizons(lifetime_years)
        ]
        financing_scenario = FinancingScenario(
            down_payment_inr=down_payment_inr,
            loan_amount_inr=loan_amount,
            interest_rate_pct=interest_rate_pct,
            tenure_years=tenure_years,
            monthly_emi_inr=emi.monthly_emi,
            total_interest_inr=emi.total_interest_inr,
            total_payment_inr=emi.total_payment_inr,
            yearly=financed_years,
            payback=financed_payback,
            horizons=financed_horizons,
        )

    replacement_note = (
        f"; a one-time component replacement (e.g. inverter) of Rs {inverter_cost_per_kwp:,.0f}/kWp "
        f"is assumed in year {inverter_year}"
        if inverter_year is not None
        else "; no component replacement is assumed within the system lifetime"
    )
    method_notes = (
        f"Year-1 generation degraded at {degradation:.1%}/yr; tariff escalated at {escalation:.1%}/yr "
        f"from Rs {base_tariff:g}/unit; {self_consumption_basis.lower()}; export valued at "
        f"Rs {export_tariff:g}/unit; maintenance at Rs {maintenance_per_kwp:,.0f}/kWp/yr{replacement_note}; "
        f"projected over the configured {lifetime_years}-year system lifetime."
    )

    return FinancialProjectionResult(
        capacity_kwp=capacity_kwp,
        initial_investment_inr=initial_investment,
        system_lifetime_years=lifetime_years,
        degradation_pct_per_year=degradation * 100.0,
        tariff_escalation_pct_per_year=escalation * 100.0,
        self_consumption_ratio_year1=(
            upfront_years[0].self_consumption_kwh / upfront_years[0].generation_kwh
            if upfront_years and upfront_years[0].generation_kwh > 0
            else 0.0
        ),
        self_consumption_basis=self_consumption_basis,
        yearly=upfront_years,
        three_year_summary=three_year_summary,
        horizons=horizons,
        payback=payback,
        lifetime_roi_pct=lifetime_roi,
        financing=financing_scenario,
        method_notes=method_notes,
        assumptions_version=assumptions_version,
    )
