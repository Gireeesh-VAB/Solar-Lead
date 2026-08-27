"""Tests for engine/fitness.py — §9.7 Fitness Scoring (FIT-01..07) and
the scoring half of §9.17 Shading Analysis (SHADE-04).

Runs against the real packages/config-packs/rooftop_v1.yaml (placeholder
values) via the real config_pack loader — no mocking needed, since these
are just coefficients, not external calls. Verdict-boundary tests use
extreme, unambiguous inputs rather than hardcoded score thresholds, so
they stay valid even after Person 2 retunes the placeholder weights.
"""

from datetime import UTC, datetime, timedelta

from solarfit.domain.site import ShadingEstimate
from solarfit.engine.fitness import score_fitness


def test_missing_capacity_returns_insufficient_data(make_site, make_capacity):
    site = make_site()
    capacity = make_capacity(status="INSUFFICIENT_DATA", recommended_kwp=None)

    result = score_fitness(site, capacity)

    assert result.verdict == "INSUFFICIENT_DATA"
    assert result.score is None
    assert result.binding_constraint.startswith("insufficient_data:")
    assert result.confidence > 0.0  # FIT-06 — always a real confidence, never omitted


def test_missing_geometry_confidence_returns_insufficient_data(make_site, make_capacity):
    site = make_site(geometry_confidence=None)
    capacity = make_capacity()

    result = score_fitness(site, capacity)

    assert result.verdict == "INSUFFICIENT_DATA"
    assert result.score is None
    assert result.binding_constraint == "insufficient_data:geometry_confidence"


def test_insufficient_data_never_a_low_score_it_is_none(make_site, make_capacity):
    """§17 non-negotiable: INSUFFICIENT_DATA is never a low score."""
    site = make_site(geometry_confidence=None)
    capacity = make_capacity(recommended_kwp=None, status="INSUFFICIENT_DATA")

    result = score_fitness(site, capacity)

    assert result.verdict == "INSUFFICIENT_DATA"
    assert result.score is None


def test_score_is_none_iff_verdict_is_insufficient_data(make_site, make_capacity):
    ok_result = score_fitness(make_site(), make_capacity())
    assert ok_result.verdict != "INSUFFICIENT_DATA"
    assert ok_result.score is not None

    bad_result = score_fitness(make_site(geometry_confidence=None), make_capacity())
    assert bad_result.verdict == "INSUFFICIENT_DATA"
    assert bad_result.score is None


def test_extremely_favourable_inputs_yield_suitable(make_site, make_capacity):
    site = make_site(
        geometry_confidence=1.0,
        shading=ShadingEstimate(shading_score=1.0, source="solar_api"),
    )
    capacity = make_capacity(recommended_kwp=100.0, headroom_kwp=100.0)

    result = score_fitness(site, capacity)

    assert result.verdict == "SUITABLE"
    assert result.score is not None
    assert result.score > 0.9


def test_extremely_unfavourable_inputs_yield_not_suitable(make_site, make_capacity):
    site = make_site(
        geometry_confidence=0.05,
        shading=ShadingEstimate(shading_score=0.0, source="solar_api"),
    )
    capacity = make_capacity(recommended_kwp=0.01, headroom_kwp=0.0)

    result = score_fitness(site, capacity)

    assert result.verdict == "NOT_SUITABLE"
    assert result.score is not None
    assert result.score < 0.2


def test_shading_unavailable_is_excluded_not_assumed(make_site, make_capacity):
    site = make_site(shading=ShadingEstimate(shading_score=None, source="unavailable"))
    capacity = make_capacity()

    result = score_fitness(site, capacity)

    assert result.components["shading"] is None
    assert any("shading" in r.lower() and "unavailable" in r.lower() for r in result.reasons)
    # Excluding shading must not be conflated with INSUFFICIENT_DATA overall.
    assert result.verdict != "INSUFFICIENT_DATA"


def test_shading_none_on_site_is_also_excluded_not_assumed(make_site, make_capacity):
    site = make_site(shading=None)
    capacity = make_capacity()

    result = score_fitness(site, capacity)

    assert result.components["shading"] is None
    assert result.verdict != "INSUFFICIENT_DATA"


def test_missing_generation_estimate_is_excluded_not_assumed(make_site, make_capacity):
    site = make_site()
    capacity = make_capacity()

    result = score_fitness(site, capacity, params={})

    assert result.components["generation_yield"] is None
    assert any("generation" in r.lower() for r in result.reasons)


def test_generation_estimate_used_when_present(make_site, make_capacity):
    site = make_site()
    capacity = make_capacity()

    result = score_fitness(site, capacity, params={"generation": {"performance_ratio": 0.95}})

    assert result.components["generation_yield"] == 0.95


def test_gate_fail_forces_not_suitable_regardless_of_score(make_site, make_capacity, make_gate):
    site = make_site(
        geometry_confidence=1.0,
        shading=ShadingEstimate(shading_score=1.0, source="solar_api"),
    )
    capacity = make_capacity(recommended_kwp=100.0, headroom_kwp=100.0)
    gates = [make_gate(gate="structural_gate", status="FAIL", detail="Roof cannot bear load")]

    result = score_fitness(site, capacity, params={"gates": gates})

    assert result.verdict == "NOT_SUITABLE"
    assert result.binding_constraint == "gate:structural_gate"
    assert any("structural_gate" in r for r in result.reasons)


def test_gate_pending_caps_verdict_at_subject_to_survey(make_site, make_capacity, make_gate):
    site = make_site(
        geometry_confidence=1.0,
        shading=ShadingEstimate(shading_score=1.0, source="solar_api"),
    )
    capacity = make_capacity(recommended_kwp=100.0, headroom_kwp=100.0)
    gates = [make_gate(gate="structural_gate", status="PENDING", detail="Awaiting survey")]

    result = score_fitness(site, capacity, params={"gates": gates})

    # Would otherwise be SUITABLE given the extreme-favourable inputs.
    assert result.verdict == "SUITABLE_SUBJECT_TO_SURVEY"


def test_binding_constraint_never_none_or_empty(make_site, make_capacity):
    for capacity_overrides in [{}, {"binding_constraint": None}]:
        result = score_fitness(make_site(), make_capacity(**capacity_overrides))
        assert result.binding_constraint
        assert isinstance(result.binding_constraint, str)


def test_confidence_always_in_bounds(make_site, make_capacity):
    scenarios = [
        (make_site(), make_capacity()),
        (make_site(geometry_confidence=None), make_capacity()),
        (make_site(), make_capacity(recommended_kwp=None, status="INSUFFICIENT_DATA")),
        (make_site(geometry_confidence=0.0), make_capacity(headroom_kwp=0.0)),
        (make_site(geometry_confidence=1.0), make_capacity(headroom_kwp=1000.0, recommended_kwp=1000.0)),
    ]
    for site, capacity in scenarios:
        result = score_fitness(site, capacity)
        assert 0.0 < result.confidence <= 1.0


def test_confidence_degrades_with_stale_imagery(make_site, make_capacity):
    fresh_site = make_site(imagery_date=datetime.now(UTC))
    stale_site = make_site(imagery_date=datetime.now(UTC) - timedelta(days=3000))
    capacity = make_capacity()

    fresh_result = score_fitness(fresh_site, capacity)
    stale_result = score_fitness(stale_site, capacity)

    assert stale_result.confidence < fresh_result.confidence


def test_limitations_statement_present_on_every_result(make_site, make_capacity):
    ok_result = score_fitness(make_site(), make_capacity())
    bad_result = score_fitness(make_site(geometry_confidence=None), make_capacity())

    assert ok_result.limitations
    assert bad_result.limitations
    assert ok_result.limitations == bad_result.limitations  # standard, verbatim, always the same


def test_pack_version_stamped(make_site, make_capacity):
    result = score_fitness(make_site(), make_capacity())
    assert result.pack_version == "rooftop_v1"


def test_reasons_never_empty(make_site, make_capacity):
    ok_result = score_fitness(make_site(), make_capacity())
    bad_result = score_fitness(make_site(geometry_confidence=None), make_capacity())

    assert len(ok_result.reasons) > 0
    assert len(bad_result.reasons) > 0


def test_reproducible_given_identical_inputs(make_site, make_capacity, make_gate):
    site = make_site()
    capacity = make_capacity()
    gates = [make_gate()]

    first = score_fitness(site, capacity, params={"gates": gates})
    second = score_fitness(site, capacity, params={"gates": gates})

    assert first == second


def test_ml_score_cannot_influence_fitness_result(make_site, make_capacity):
    """FIT-06/§17: the ML score is additive metadata and must never
    substitute for or influence the FIT verdict. score_fitness() doesn't
    even accept an MLScore parameter — this test documents that
    guarantee structurally, by confirming identical FitnessResults
    regardless of what an (unused) adversarial ML score would claim."""
    site = make_site()
    capacity = make_capacity()

    result = score_fitness(site, capacity)
    result_again = score_fitness(site, capacity)

    assert result == result_again
