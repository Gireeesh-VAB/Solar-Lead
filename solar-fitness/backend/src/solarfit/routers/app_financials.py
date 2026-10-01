"""FIN-02 — Solar Financial Analysis / ROI module.

Customer-facing: GET /app/checks/{check_id}/financial-projection — the
year-by-year projection, 3-year summary, long-term horizons, payback,
lifetime ROI, and (by default) an upfront-vs-financed comparison, built
on top of the FIN-01 estimate and generation figure already persisted on
that check's latest assessment (routers/assessments.py::
orchestrate_assessment() — never recomputed here).

Admin-facing: GET/PATCH /app/admin/financial-config — the versioned
assumptions repositories/financial_config.py stores (escalation, export
rate, self-consumption default, maintenance, financing defaults). PATCH
always creates a NEW version rather than editing in place, so a
previously computed financial_projections row (which stamps the version
it used) never silently changes meaning.

Ownership/auth reuses app_checks.py's own helpers — a "check" IS a Site
(see that module's docstring), so financial-projection access follows
the identical owner_org-via-synthetic-id rule the rest of the checks
surface already applies, rather than inventing a second ownership check.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, current_user, require_role
from solarfit.db import get_session
from solarfit.engine.financial_projection import project_financials
from solarfit.engine.seasonal_consumption import estimate_seasonal_consumption
from solarfit.engine.seasonal_financial_projection import project_seasonal_financials
from solarfit.packs.config_pack import get_electricity_tariff_inr_per_kwh
from solarfit.repositories import assessments as assessments_repo
from solarfit.repositories import audit as audit_repo
from solarfit.repositories import financial_config as financial_config_repo
from solarfit.repositories import financial_projections as financial_projections_repo
from solarfit.repositories import sites as sites_repo
from solarfit.routers.app_checks import _readable_check_or_404
from solarfit.routers.common import actor_audit_fields

router = APIRouter(tags=["app-financials"])


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# --------------------------------------------------------------------- #
# customer-facing projection
# --------------------------------------------------------------------- #


class YearProjectionOut(_CamelModel):
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


class HorizonSummaryOut(_CamelModel):
    horizon_years: int
    total_generation_kwh: float
    total_gross_savings_inr: float
    total_costs_inr: float
    total_net_savings_inr: float
    cumulative_roi_pct: float
    investment_recovered: bool
    profit_after_recovery_inr: float


class PaybackOut(_CamelModel):
    recovered: bool
    payback_year: int | None
    payback_years: float | None
    payback_months: int | None
    amount_recovered_before_payback_inr: float


class FinancingScenarioOut(_CamelModel):
    down_payment_inr: float
    loan_amount_inr: float
    interest_rate_pct: float
    tenure_years: float
    monthly_emi_inr: float
    total_interest_inr: float
    total_payment_inr: float
    yearly: list[YearProjectionOut]
    payback: PaybackOut
    horizons: list[HorizonSummaryOut]


class SeasonEstimateOut(_CamelModel):
    monthly_kwh: float
    months: int
    annual_kwh: float
    estimated: bool


class SeasonalConsumptionOut(_CamelModel):
    """FIN-03 — §5's "Your electricity profile" card. Absent entirely
    (see FinancialProjectionOut.electricity_profile below) when the
    customer gave neither a kWh reading nor a bill amount — never a
    fabricated seasonal split."""

    seasons: dict[str, SeasonEstimateOut]
    annual_kwh: float
    average_monthly_kwh: float
    highest_monthly_kwh: float
    lowest_monthly_kwh: float
    source: str
    basis: str


class SolarRequirementOut(_CamelModel):
    """FIN-03 §6/§7/§8 — electricity-based sizing shown ALONGSIDE the
    roof's own resolved capacity, never in place of it. recommended_kwp
    is always min(electricity_required_kwp, roof_capacity_kwp) — this
    never exceeds what the roof can physically hold."""

    electricity_required_kwp: float
    roof_capacity_kwp: float
    recommended_kwp: float
    coverage_pct: float


class SeasonFinancialOut(_CamelModel):
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


class SeasonalFinancialOut(_CamelModel):
    seasons: dict[str, SeasonFinancialOut]
    annual_generation_kwh: float
    annual_gross_benefit_inr: float
    annual_maintenance_inr: float
    annual_net_benefit_inr: float
    annual_emi_inr: float
    annual_net_benefit_after_emi_inr: float
    generation_shares: dict[str, float]
    generation_share_source: str


class FinancialProjectionOut(_CamelModel):
    capacity_kwp: float
    initial_investment_inr: float
    system_lifetime_years: int
    degradation_pct_per_year: float
    tariff_escalation_pct_per_year: float
    self_consumption_ratio_year1: float
    self_consumption_basis: str
    yearly: list[YearProjectionOut]
    three_year_summary: HorizonSummaryOut
    horizons: list[HorizonSummaryOut]
    payback: PaybackOut
    lifetime_roi_pct: float
    financing: FinancingScenarioOut | None
    method_notes: str
    assumptions_version: int
    # FIN-03 — additive. All three are None together only when there's no
    # consumption estimate at all (neither a kWh reading nor a bill on
    # file) — the year-wise figures above are unaffected either way.
    electricity_profile: SeasonalConsumptionOut | None = None
    solar_requirement: SolarRequirementOut | None = None
    seasonal: SeasonalFinancialOut | None = None


def _horizon_out(h) -> HorizonSummaryOut:
    return HorizonSummaryOut(**asdict(h))


def _payback_out(p) -> PaybackOut:
    return PaybackOut(**asdict(p))


def _year_out(y) -> YearProjectionOut:
    return YearProjectionOut(**asdict(y))


def _seasonal_consumption_out(consumption) -> SeasonalConsumptionOut:
    return SeasonalConsumptionOut(
        seasons={
            name: SeasonEstimateOut(**asdict(season)) for name, season in consumption.seasons.items()
        },
        annual_kwh=consumption.annual_kwh,
        average_monthly_kwh=consumption.average_monthly_kwh,
        highest_monthly_kwh=consumption.highest_monthly_kwh,
        lowest_monthly_kwh=consumption.lowest_monthly_kwh,
        source=consumption.source,
        basis=consumption.basis,
    )


def _seasonal_financial_out(seasonal) -> SeasonalFinancialOut:
    return SeasonalFinancialOut(
        seasons={name: SeasonFinancialOut(**asdict(s)) for name, s in seasonal.seasons.items()},
        annual_generation_kwh=seasonal.annual_generation_kwh,
        annual_gross_benefit_inr=seasonal.annual_gross_benefit_inr,
        annual_maintenance_inr=seasonal.annual_maintenance_inr,
        annual_net_benefit_inr=seasonal.annual_net_benefit_inr,
        annual_emi_inr=seasonal.annual_emi_inr,
        annual_net_benefit_after_emi_inr=seasonal.annual_net_benefit_after_emi_inr,
        generation_shares=seasonal.generation_shares,
        generation_share_source=seasonal.generation_share_source,
    )


def _projection_out(
    result,
    *,
    electricity_profile: SeasonalConsumptionOut | None = None,
    solar_requirement: SolarRequirementOut | None = None,
    seasonal: SeasonalFinancialOut | None = None,
) -> FinancialProjectionOut:
    return FinancialProjectionOut(
        capacity_kwp=result.capacity_kwp,
        initial_investment_inr=result.initial_investment_inr,
        system_lifetime_years=result.system_lifetime_years,
        degradation_pct_per_year=result.degradation_pct_per_year,
        tariff_escalation_pct_per_year=result.tariff_escalation_pct_per_year,
        self_consumption_ratio_year1=result.self_consumption_ratio_year1,
        self_consumption_basis=result.self_consumption_basis,
        yearly=[_year_out(y) for y in result.yearly],
        three_year_summary=_horizon_out(result.three_year_summary),
        horizons=[_horizon_out(h) for h in result.horizons],
        payback=_payback_out(result.payback),
        lifetime_roi_pct=result.lifetime_roi_pct,
        financing=(
            FinancingScenarioOut(
                down_payment_inr=result.financing.down_payment_inr,
                loan_amount_inr=result.financing.loan_amount_inr,
                interest_rate_pct=result.financing.interest_rate_pct,
                tenure_years=result.financing.tenure_years,
                monthly_emi_inr=result.financing.monthly_emi_inr,
                total_interest_inr=result.financing.total_interest_inr,
                total_payment_inr=result.financing.total_payment_inr,
                yearly=[_year_out(y) for y in result.financing.yearly],
                payback=_payback_out(result.financing.payback),
                horizons=[_horizon_out(h) for h in result.financing.horizons],
            )
            if result.financing
            else None
        ),
        method_notes=result.method_notes,
        assumptions_version=result.assumptions_version,
        electricity_profile=electricity_profile,
        solar_requirement=solar_requirement,
        seasonal=seasonal,
    )


@router.get("/app/checks/{check_id}/financial-projection", response_model=FinancialProjectionOut)
def get_check_financial_projection(
    check_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    financing: Annotated[bool, Query(description="Include the financed-purchase comparison")] = True,
    down_payment_pct: Annotated[float | None, Query(ge=0, le=100)] = None,
    interest_rate_pct: Annotated[float | None, Query(ge=0, le=100)] = None,
    tenure_years: Annotated[float | None, Query(gt=0, le=30)] = None,
) -> FinancialProjectionOut:
    """Never recomputes capacity/generation/cost — reads them straight off
    this check's latest persisted assessment (the same numbers the
    result page's existing FinancialCard already shows) and projects
    them forward. 404 when no assessment has run yet, same discipline as
    every other .../checks/{id}/... read in this codebase. Uses
    _readable_check_or_404 (not the stricter _owned_check_or_404) so an
    admin can see the same projection chart a customer does when
    reviewing a check via the admin assessment page's Feasibility
    button."""
    _readable_check_or_404(session, check_id, user)
    assessment = assessments_repo.get_latest_by_site(session, check_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no assessment has run for this check yet")

    capacity_kwp = (assessment.capacity or {}).get("recommended_kwp")
    generation_kwh = (assessment.generation or {}).get("estimated_kwh_per_year")
    specific_yield = (assessment.generation or {}).get("specific_yield_kwh_per_kwp")
    pvgis_monthly_kwh = (assessment.generation or {}).get("pvgis_monthly_kwh")

    bill_low, bill_high = sites_repo.get_bill_range(session, check_id)
    lowest_kwh, highest_kwh = sites_repo.get_consumption_range(session, check_id)

    assumptions_row = financial_config_repo.get_current(session)
    assumptions = assumptions_row.values

    # FIN-03 — the one, central consumption estimate every seasonal AND
    # year-wise figure below is built from. Prefers the customer's own
    # kWh reading; falls back to their ₹ bill amount via the config-pack
    # tariff only when no kWh reading was given (§1: never size solar
    # directly off a rupee figure).
    seasonal_consumption = estimate_seasonal_consumption(
        highest_consumption_kwh=highest_kwh,
        lowest_consumption_kwh=lowest_kwh,
        monthly_bill_high_inr=bill_high,
        monthly_bill_low_inr=bill_low,
        tariff_inr_per_kwh=get_electricity_tariff_inr_per_kwh(),
        rainy_factor_pct=assumptions.get("rainy_season_factor_pct", 50.0),
        summer_months=assumptions.get("summer_months", 4),
        rainy_months=assumptions.get("rainy_months", 4),
        winter_months=assumptions.get("winter_months", 4),
    )

    financing_overrides = {
        k: v
        for k, v in {
            "down_payment_pct": down_payment_pct,
            "interest_rate_pct": interest_rate_pct,
            "tenure_years": tenure_years,
        }.items()
        if v is not None
    }

    result = project_financials(
        capacity_kwp=capacity_kwp,
        annual_generation_kwh=generation_kwh,
        financial_estimate=assessment.financial_estimate,
        assumptions=assumptions,
        assumptions_version=assumptions_row.id,
        annual_consumption_kwh=seasonal_consumption.annual_kwh if seasonal_consumption else None,
        financing_enabled=financing,
        financing_overrides=financing_overrides or None,
    )
    if result is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "not enough resolved capacity/generation/cost data to project financials for this check",
        )

    # FIN-03 §6/§7/§8 — electricity-based sizing shown ALONGSIDE the
    # roof's own resolved capacity, never in place of it. Uses the SAME
    # specific yield the real generation engine already resolved for
    # this roof (never CON-05's own separate fallback constant), so this
    # figure can never quietly disagree with the sizing the rest of the
    # app already used.
    solar_requirement_out = None
    if seasonal_consumption is not None and specific_yield and specific_yield > 0 and capacity_kwp:
        electricity_required_kwp = seasonal_consumption.annual_kwh / specific_yield
        recommended_kwp = min(electricity_required_kwp, capacity_kwp)
        coverage_pct = (
            (generation_kwh / seasonal_consumption.annual_kwh) * 100.0
            if generation_kwh and seasonal_consumption.annual_kwh > 0
            else 0.0
        )
        solar_requirement_out = SolarRequirementOut(
            electricity_required_kwp=electricity_required_kwp,
            roof_capacity_kwp=capacity_kwp,
            recommended_kwp=recommended_kwp,
            coverage_pct=coverage_pct,
        )

    # FIN-03 §9/§10/§12 — the season-wise companion view, built from the
    # SAME assumptions/generation/EMI the year-wise result above already
    # resolved (never a second calculation engine).
    seasonal_out = None
    if seasonal_consumption is not None and generation_kwh:
        seasonal_result = project_seasonal_financials(
            capacity_kwp=capacity_kwp,
            annual_generation_kwh=generation_kwh,
            pvgis_monthly_kwh=pvgis_monthly_kwh,
            consumption=seasonal_consumption,
            assumptions=assumptions,
            monthly_emi_inr=result.financing.monthly_emi_inr if result.financing else 0.0,
        )
        seasonal_out = _seasonal_financial_out(seasonal_result)

    out = _projection_out(
        result,
        electricity_profile=(
            _seasonal_consumption_out(seasonal_consumption) if seasonal_consumption is not None else None
        ),
        solar_requirement=solar_requirement_out,
        seasonal=seasonal_out,
    )
    financial_projections_repo.save_projection(
        session,
        assessment_id=assessment.id,
        assumptions_version=assumptions_row.id,
        financing_input=financing_overrides or None,
        result=out.model_dump(by_alias=False),
    )
    session.commit()
    return out


# --------------------------------------------------------------------- #
# admin-facing assumptions configuration
# --------------------------------------------------------------------- #


class SeasonCalendarMonthsModel(_CamelModel):
    """Which calendar months (1=Jan..12=Dec) belong to each season, used
    ONLY to bucket a real PVGIS monthly breakdown when one exists — see
    engine/seasonal_financial_projection.py::seasonal_generation_shares().
    Never used for consumption seasonalization (that's purely the
    configured month COUNTS below, matching the spec's own examples)."""

    summer: list[int] = Field(default_factory=lambda: [3, 4, 5, 6])
    rainy: list[int] = Field(default_factory=lambda: [7, 8, 9, 10])
    winter: list[int] = Field(default_factory=lambda: [11, 12, 1, 2])


class FinancialAssumptionsOut(_CamelModel):
    version: int
    tariff_escalation_pct_per_year: float
    export_tariff_inr_per_kwh: float
    default_self_consumption_ratio: float
    annual_maintenance_cost_inr_per_kwp: float
    inverter_replacement_year: int | None = None
    inverter_replacement_cost_inr_per_kwp: float | None = None
    financing_default_down_payment_pct: float
    financing_default_interest_rate_pct: float
    financing_default_tenure_years: float
    # FIN-03 — all defaulted so a row saved before these keys existed
    # (an older admin_config version) still deserializes cleanly.
    annual_consumption_growth_pct: float = 2.0
    rainy_season_factor_pct: float = 50.0
    summer_months: int = 4
    rainy_months: int = 4
    winter_months: int = 4
    summer_generation_share: float = 0.36
    rainy_generation_share: float = 0.28
    winter_generation_share: float = 0.36
    season_calendar_months: SeasonCalendarMonthsModel = Field(default_factory=SeasonCalendarMonthsModel)
    updated_by: str | None = None
    note: str | None = None
    updated_at: str


class SetFinancialAssumptionsRequest(_CamelModel):
    tariff_escalation_pct_per_year: float = Field(ge=0, le=50)
    export_tariff_inr_per_kwh: float = Field(ge=0)
    default_self_consumption_ratio: float = Field(ge=0, le=1)
    annual_maintenance_cost_inr_per_kwp: float = Field(ge=0)
    inverter_replacement_year: int | None = Field(default=None, ge=1, le=50)
    inverter_replacement_cost_inr_per_kwp: float | None = Field(default=None, ge=0)
    financing_default_down_payment_pct: float = Field(ge=0, le=100)
    financing_default_interest_rate_pct: float = Field(ge=0, le=50)
    financing_default_tenure_years: float = Field(gt=0, le=30)
    annual_consumption_growth_pct: float = Field(ge=0, le=50)
    rainy_season_factor_pct: float = Field(ge=0, le=100)
    summer_months: int = Field(ge=1, le=11)
    rainy_months: int = Field(ge=1, le=11)
    winter_months: int = Field(ge=1, le=11)
    summer_generation_share: float = Field(ge=0, le=1)
    rainy_generation_share: float = Field(ge=0, le=1)
    winter_generation_share: float = Field(ge=0, le=1)
    season_calendar_months: SeasonCalendarMonthsModel = Field(default_factory=SeasonCalendarMonthsModel)
    note: str | None = None

    @model_validator(mode="after")
    def _seasons_must_reconcile(self) -> "SetFinancialAssumptionsRequest":
        total_months = self.summer_months + self.rainy_months + self.winter_months
        if total_months != 12:
            raise ValueError(
                f"summer + rainy + winter months must total 12, got {total_months}"
            )
        share_total = self.summer_generation_share + self.rainy_generation_share + self.winter_generation_share
        if abs(share_total - 1.0) > 0.01:
            raise ValueError(
                f"summer + rainy + winter generation shares must total 1.0 (100%), got {share_total:.3f}"
            )
        return self


def _assumptions_out(row) -> FinancialAssumptionsOut:
    return FinancialAssumptionsOut(
        version=row.id,
        updated_by=row.created_by,
        note=row.note,
        updated_at=row.created_at.isoformat(),
        **row.values,
    )


@router.get("/app/admin/financial-config", response_model=FinancialAssumptionsOut)
def get_financial_config(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> FinancialAssumptionsOut:
    return _assumptions_out(financial_config_repo.get_current(session))


@router.patch("/app/admin/financial-config", response_model=FinancialAssumptionsOut)
def set_financial_config(
    payload: SetFinancialAssumptionsRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> FinancialAssumptionsOut:
    """Always inserts a NEW version — never edits a prior one in place,
    so a stored financial_projections row's assumptions_version keeps
    meaning exactly what it meant when it was computed."""
    values = payload.model_dump(by_alias=False, exclude={"note"})
    row = financial_config_repo.create_version(
        session, values=values, created_by=admin.email, note=payload.note
    )
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(admin),
        action="platform.financial_config_updated",
        target=f"financial_assumptions:v{row.id}",
        entity_type="financial_config",
        details=f"{admin.email} published financial-assumptions version {row.id}"
        + (f" — {payload.note}" if payload.note else ""),
    )
    session.commit()
    return _assumptions_out(row)
