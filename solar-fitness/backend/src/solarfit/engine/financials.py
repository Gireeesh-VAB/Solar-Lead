"""FIN-01 — an engine ESTIMATE of project cost, subsidy, and payback.

Distinct from AssessmentRow.financial_feasibility (routers/
app_assessments.py::FinancialFeasibilityOut) — that field is a real,
admin-entered quote/negotiated figure, deliberately never computed by
the engine (same "an admin has to look up or negotiate this" reasoning
as grid_feasibility). This module produces the customer-facing
INDICATIVE figure shown before any real quote exists, same relationship
as engine/generation.py's estimate sitting beside admin-owned fields.

Every assumption (cost/kWp, subsidy scheme, tariff, degradation) comes
from the config pack — see packs/config_pack.py's FIN-01 accessors —
never hardcoded here, so a pack swap changes the estimate with no code
change (CFG-01).

No fabrication: a figure that depends on generation (savings, payback,
lifetime savings) is None, not a guess, when no generation estimate was
available. A site type outside the subsidy scheme gets
subsidy_applicable=False and subsidy_amount_inr=None, never a 0 that
would read as "we checked and there's no subsidy" when really "this
scheme has never applied to you" is the honest fact of the matter —
same distinction, so kept the same way.
"""

from solarfit.domain.site import RoofSiteType
from solarfit.packs import config_pack

_SITE_TYPE_LABEL: dict[str, str] = {
    "ROOFTOP_RESIDENTIAL": "Residential",
    "ROOFTOP_CI": "Commercial & Industrial",
    "ROOFTOP_GOVT": "Government",
}


def _explain_subsidy(
    site_type: RoofSiteType,
    capacity_kwp: float,
    scheme: dict,
    *,
    subsidy_applicable: bool,
    subsidy_capacity_considered_kwp: float | None,
    subsidy_amount: float | None,
) -> tuple[list[str], str | None]:
    """FIN-01 explainability. Deterministic, template-based — every
    sentence is derived straight from the same numbers that produced
    subsidy_amount_inr above (see estimate_financials()), never
    free-form/generated text, same discipline as
    engine/fitness.py::_explain_confidence()."""
    category_label = _SITE_TYPE_LABEL.get(site_type, site_type)

    if not subsidy_applicable:
        eligible_labels = ", ".join(
            _SITE_TYPE_LABEL.get(t, t) for t in scheme["eligible_site_types"]
        )
        reason = (
            f"This scheme currently applies to {eligible_labels} sites only; "
            f"your site is categorised as {category_label}."
        )
        return [], reason

    assert subsidy_capacity_considered_kwp is not None
    assert subsidy_amount is not None

    capacity_sentence = f"Eligible system capacity: {subsidy_capacity_considered_kwp:.1f} kW"
    if capacity_kwp > scheme["max_capacity_kwp"]:
        capacity_sentence += (
            f" (capped at the scheme's {scheme['max_capacity_kwp']:.1f} kW limit; "
            f"your recommended system is {capacity_kwp:.1f} kW)."
        )
    else:
        capacity_sentence += "."

    final_sentence = f"Final eligible subsidy: Rs {subsidy_amount:,.0f}"
    if subsidy_amount >= scheme["max_amount_inr"]:
        final_sentence += f" (capped at the scheme's Rs {scheme['max_amount_inr']:,.0f} maximum)."
    else:
        final_sentence += (
            f" ({subsidy_capacity_considered_kwp:.1f} kW x Rs {scheme['inr_per_kwp']:,.0f}/kW)."
        )

    explanation = [
        capacity_sentence,
        f"Customer category: {category_label} — eligible under this scheme.",
        f"Applicable subsidy rate: Rs {scheme['inr_per_kwp']:,.0f} per kW.",
        f"Maximum applicable subsidy under this scheme: Rs {scheme['max_amount_inr']:,.0f}.",
        final_sentence,
    ]
    return explanation, None


def estimate_financials(
    site_type: RoofSiteType,
    capacity_kwp: float | None,
    annual_generation_kwh: float | None,
    params: dict | None = None,
) -> dict | None:
    """FIN-01. `params` is accepted for forward compatibility (e.g. a
    future real tariff/consumer-category override) but unused today —
    same shape as engine/generation.py's `params` argument."""
    del params
    if not capacity_kwp or capacity_kwp <= 0:
        return None

    method_notes: list[str] = []

    cost_per_kwp = config_pack.get_installation_cost_inr_per_kwp()
    panel_cost = cost_per_kwp["panel"] * capacity_kwp
    inverter_cost = cost_per_kwp["inverter"] * capacity_kwp
    mounting_structure_cost = cost_per_kwp["mounting_structure"] * capacity_kwp
    electrical_material_cost = cost_per_kwp["electrical_material"] * capacity_kwp
    installation_cost = cost_per_kwp["installation_labor"] * capacity_kwp
    total_project_cost = (
        panel_cost + inverter_cost + mounting_structure_cost + electrical_material_cost + installation_cost
    )
    method_notes.append(f"cost estimated at {sum(cost_per_kwp.values()):,.0f} INR/kWp (config-pack placeholder)")

    scheme = config_pack.get_subsidy_scheme()
    subsidy_applicable = site_type in scheme["eligible_site_types"]
    subsidy_amount: float | None = None
    subsidy_capacity: float | None = None
    if subsidy_applicable:
        subsidy_capacity = min(capacity_kwp, scheme["max_capacity_kwp"])
        subsidy_amount = min(subsidy_capacity * scheme["inr_per_kwp"], scheme["max_amount_inr"])
        method_notes.append(f"subsidy estimated for {site_type} under the configured central scheme")
    else:
        method_notes.append(f"no subsidy scheme configured for {site_type}")

    subsidy_explanation, subsidy_ineligibility_reason = _explain_subsidy(
        site_type,
        capacity_kwp,
        scheme,
        subsidy_applicable=subsidy_applicable,
        subsidy_capacity_considered_kwp=subsidy_capacity,
        subsidy_amount=subsidy_amount,
    )

    customer_contribution = total_project_cost - (subsidy_amount or 0.0)

    tariff = config_pack.get_electricity_tariff_inr_per_kwh()
    annual_savings: float | None = None
    monthly_savings: float | None = None
    payback_period_years: float | None = None
    ten_year_savings: float | None = None
    twenty_year_savings: float | None = None
    lifetime_years = config_pack.get_system_lifetime_years()

    if annual_generation_kwh is not None and annual_generation_kwh > 0:
        annual_savings = annual_generation_kwh * tariff
        monthly_savings = annual_savings / 12.0
        payback_period_years = (
            customer_contribution / annual_savings if annual_savings > 0 and customer_contribution > 0 else None
        )
        degradation = config_pack.get_panel_degradation_pct_per_year() / 100.0
        ten_year_savings = _projected_savings(annual_savings, degradation, years=10, lifetime_years=lifetime_years)
        twenty_year_savings = _projected_savings(annual_savings, degradation, years=20, lifetime_years=lifetime_years)
        method_notes.append(f"savings projected at Rs {tariff:g}/unit with {degradation:.1%}/yr panel degradation")
    else:
        method_notes.append("no generation estimate available — savings/payback not computed")

    return {
        "panel_cost_inr": panel_cost,
        "inverter_cost_inr": inverter_cost,
        "mounting_structure_cost_inr": mounting_structure_cost,
        "electrical_material_cost_inr": electrical_material_cost,
        "installation_cost_inr": installation_cost,
        "total_project_cost_inr": total_project_cost,
        "subsidy_applicable": subsidy_applicable,
        "subsidy_category": site_type,
        "subsidy_amount_inr": subsidy_amount,
        "subsidy_scheme_name": scheme.get("name"),
        "subsidy_scheme_max_amount_inr": scheme["max_amount_inr"],
        "subsidy_rate_inr_per_kwp": scheme["inr_per_kwp"],
        "subsidy_scheme_max_capacity_kwp": scheme["max_capacity_kwp"],
        "subsidy_capacity_considered_kwp": subsidy_capacity,
        "subsidy_ineligibility_reason": subsidy_ineligibility_reason,
        "subsidy_explanation": subsidy_explanation,
        "customer_contribution_inr": customer_contribution,
        "monthly_savings_inr": monthly_savings,
        "annual_savings_inr": annual_savings,
        "payback_period_years": payback_period_years,
        "ten_year_savings_inr": ten_year_savings,
        "twenty_year_savings_inr": twenty_year_savings,
        "estimated_system_lifetime_years": lifetime_years,
        "method_notes": "; ".join(method_notes),
    }


def _projected_savings(annual_savings_inr: float, degradation: float, *, years: int, lifetime_years: float) -> float:
    """Sum of degraded annual savings across min(years, lifetime_years)
    years — year 1 at full annual_savings_inr, each subsequent year
    reduced by `degradation` compounding (same convention as panel
    output warranties are usually quoted)."""
    horizon = min(years, int(lifetime_years))
    return sum(annual_savings_inr * ((1 - degradation) ** year) for year in range(horizon))
