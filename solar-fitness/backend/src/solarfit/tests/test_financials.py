"""FIN-01 — engine/financials.py::estimate_financials()'s subsidy
explainability. Reads expected numbers from the real config pack
(get_subsidy_scheme()) rather than hardcoding them, so this doesn't
break the moment an admin retunes the pack — same discipline as
test_financial_projection.py.
"""

from solarfit.engine.financials import estimate_financials
from solarfit.packs.config_pack import get_subsidy_scheme


def test_eligible_site_gets_a_full_subsidy_breakdown():
    scheme = get_subsidy_scheme()
    capacity_kwp = scheme["max_capacity_kwp"] / 2  # below the cap, so the rate*capacity math applies

    result = estimate_financials("ROOFTOP_RESIDENTIAL", capacity_kwp, annual_generation_kwh=None)

    assert result["subsidy_applicable"] is True
    assert result["subsidy_ineligibility_reason"] is None
    assert result["subsidy_scheme_name"] == scheme["name"]
    assert result["subsidy_scheme_max_amount_inr"] == scheme["max_amount_inr"]
    assert result["subsidy_rate_inr_per_kwp"] == scheme["inr_per_kwp"]
    assert result["subsidy_capacity_considered_kwp"] == capacity_kwp
    assert result["subsidy_amount_inr"] == capacity_kwp * scheme["inr_per_kwp"]
    assert len(result["subsidy_explanation"]) == 5
    assert any("Eligible system capacity" in s for s in result["subsidy_explanation"])
    assert any("Final eligible subsidy" in s for s in result["subsidy_explanation"])


def test_capacity_above_the_scheme_cap_is_capped_and_explained():
    scheme = get_subsidy_scheme()
    capacity_kwp = scheme["max_capacity_kwp"] * 2  # well above the cap

    result = estimate_financials("ROOFTOP_RESIDENTIAL", capacity_kwp, annual_generation_kwh=None)

    assert result["subsidy_capacity_considered_kwp"] == scheme["max_capacity_kwp"]
    expected_amount = min(scheme["max_capacity_kwp"] * scheme["inr_per_kwp"], scheme["max_amount_inr"])
    assert result["subsidy_amount_inr"] == expected_amount
    capacity_sentence = next(s for s in result["subsidy_explanation"] if "Eligible system capacity" in s)
    assert "capped at the scheme's" in capacity_sentence


def test_ineligible_category_gets_a_reason_never_a_fabricated_amount():
    scheme = get_subsidy_scheme()
    assert "ROOFTOP_CI" not in scheme["eligible_site_types"]  # sanity: this test exercises the ineligible path

    result = estimate_financials("ROOFTOP_CI", 5.0, annual_generation_kwh=None)

    assert result["subsidy_applicable"] is False
    assert result["subsidy_amount_inr"] is None
    assert result["subsidy_capacity_considered_kwp"] is None
    assert result["subsidy_explanation"] == []
    assert result["subsidy_ineligibility_reason"] is not None
    assert "Commercial" in result["subsidy_ineligibility_reason"]
    # The scheme's maximum is still surfaced for context, distinct from
    # this customer's (nonexistent) eligible amount.
    assert result["subsidy_scheme_max_amount_inr"] == scheme["max_amount_inr"]


def test_no_capacity_returns_no_estimate_at_all():
    assert estimate_financials("ROOFTOP_RESIDENTIAL", None, annual_generation_kwh=None) is None
    assert estimate_financials("ROOFTOP_RESIDENTIAL", 0.0, annual_generation_kwh=None) is None
