"""Owner: Person 4 (Scoring, USN & Assessment API).

Implements §9.7 Fitness Scoring (FIT-01..07) AND the scoring half of
§9.17 Shading Analysis (SHADE-04) of
Solar_Fitness_Engine_Development_Document_v1.2 — the deterministic,
reproducible verdict. This is the SOLE authoritative output; the ML
score (engine/ml_score.py) is additive metadata and must never override
it (FIT-06, §17).

  FIT-01  Weighted-component score from the scoring profile for the site type.
  FIT-02  Verdict: SUITABLE | SUITABLE_SUBJECT_TO_SURVEY | CONDITIONAL |
          INSUFFICIENT_DATA | NOT_SUITABLE.
  FIT-03  INSUFFICIENT_DATA takes precedence over any computed score.
  FIT-04  Confidence from geometry source, imagery recency, constraint
          completeness, gate resolution, calibration state.
  FIT-05  Human-readable reason list naming the binding constraint.
  FIT-06  Verdict/capacity always ship with confidence + binding
          constraint; this stays authoritative over the ML score.
  FIT-07  Attach the standard pre-feasibility limitations statement.
  SHADE-04  site.shading.shading_score is one of FIT-01's weighted
            components. When site.shading.source == "unavailable",
            that sub-component is excluded (never assumed zero/full)
            and its weight is redistributed across the remaining
            present components.

Assumptions (no fuller spec pins these down — flagged, not silent):
  - score is a continuous 0..1 figure, same scale as confidence, rather
    than an invented 0..100 percentage.
  - CapacityResult carries no `gates` field despite Gate's own docstring
    saying gates "modify the verdict" — gates are threaded through via
    params["gates"]: list[Gate] instead. Any FAIL gate forces
    NOT_SUITABLE regardless of the weighted score; a PENDING gate (with
    no FAIL present) caps the verdict at SUITABLE_SUBJECT_TO_SURVEY.
  - engine/generation.py's estimate_generation_kwh() isn't built yet and
    returns a plain dict with unpinned field names — the optional
    generation_yield component reads params["generation"]["performance_ratio"]
    when present, and is excluded (not defaulted) otherwise.
  - CAL-05's "feed calibration state into the confidence model" is read
    via params["calibration_state"]: float | None (0..1, None = no
    calibration data yet) rather than a direct import of
    repositories/calibration.py, since that module is still a stub as
    of this file landing — routers/assessments.py wires the real value
    through once repositories/calibration.py's Phase 1 work lands.

Depends on: solarfit.domain.constraint.CapacityResult / Gate (Person 2's
frozen contracts), solarfit.domain.site.Site (frozen, carries .shading —
see domain/site.py's ShadingEstimate).
"""

from datetime import UTC, datetime

from solarfit.domain.assessment import FitnessResult, FitnessVerdict
from solarfit.domain.constraint import CapacityResult, Gate
from solarfit.domain.site import Site
from solarfit.packs.config_pack import (
    get_fitness_capacity_adequacy_target_multiple,
    get_fitness_confidence_weights,
    get_fitness_headroom_normalization_kwp,
    get_fitness_imagery_recency_full_score_days,
    get_fitness_imagery_recency_zero_score_days,
    get_fitness_verdict_thresholds,
    get_fitness_weights,
    get_minimum_viable_kwp,
    pack_version,
)

STANDARD_LIMITATIONS = (
    "This is a pre-feasibility estimate based on remote geometry, modelled "
    "generation and rules-based scoring. It does not replace a structural, "
    "electrical or on-site engineering survey. The product prioritises "
    "candidate sites; it does not approve them."
)


def score_fitness(site: Site, capacity: CapacityResult, params: dict | None = None) -> FitnessResult:
    """FIT-01..07, SHADE-04.

    params (all optional):
      gates: list[Gate]              — CON-03 gates evaluated for this site
      generation: dict                — engine/generation.py's return value
      calibration_state: float | None — CAL-05, 0..1, None = no data yet
    """
    params = params or {}
    gates: list[Gate] = params.get("gates", [])
    generation: dict | None = params.get("generation")
    calibration_state: float | None = params.get("calibration_state")

    pv = pack_version()

    insufficient_reason = _insufficient_data_reason(site, capacity)
    if insufficient_reason is not None:
        confidence = _compute_confidence(site, capacity, gates, calibration_state, degraded=True)
        return FitnessResult(
            verdict="INSUFFICIENT_DATA",
            score=None,
            confidence=confidence,
            binding_constraint=f"insufficient_data:{insufficient_reason}",
            components={},
            reasons=[f"Insufficient data: {insufficient_reason} missing or unresolved."],
            limitations=STANDARD_LIMITATIONS,
            pack_version=pv,
        )

    components, component_reasons = _compute_components(site, capacity, generation)
    weights = _redistributed_weights(components)
    raw_score = sum(weights[name] * components[name] for name in weights)

    fail_gate = next((g for g in gates if g.status == "FAIL"), None)
    if fail_gate is not None:
        verdict: FitnessVerdict = "NOT_SUITABLE"
        raw_score = 0.0
    else:
        verdict = _verdict_from_score(raw_score)
        if verdict == "SUITABLE" and any(g.status == "PENDING" for g in gates):
            verdict = "SUITABLE_SUBJECT_TO_SURVEY"

    confidence = _compute_confidence(site, capacity, gates, calibration_state, degraded=False)

    if fail_gate is not None:
        binding_constraint = f"gate:{fail_gate.gate}"
    else:
        binding_constraint = capacity.binding_constraint or "insufficient_data:capacity"

    reasons = [f"Binding constraint: {binding_constraint}."]
    reasons.extend(component_reasons)
    if fail_gate is not None:
        reasons.append(f"Gate '{fail_gate.gate}' failed: {fail_gate.detail}.")
    for gate in gates:
        if gate.status == "PENDING":
            reasons.append(f"Gate '{gate.gate}' pending: {gate.detail}.")

    return FitnessResult(
        verdict=verdict,
        score=round(raw_score, 4),
        confidence=confidence,
        binding_constraint=binding_constraint,
        components=components,
        reasons=reasons,
        limitations=STANDARD_LIMITATIONS,
        pack_version=pv,
    )


def _insufficient_data_reason(site: Site, capacity: CapacityResult) -> str | None:
    """FIT-03. Returns the name of the first missing mandatory input, or
    None if every mandatory input is present."""
    if capacity.status == "INSUFFICIENT_DATA" or capacity.recommended_kwp is None:
        return "capacity"
    if site.geometry_confidence is None:
        return "geometry_confidence"
    return None


def _compute_components(
    site: Site, capacity: CapacityResult, generation: dict | None
) -> tuple[dict[str, float | None], list[str]]:
    """FIT-01, SHADE-04. Returns (components, reasons-for-exclusions).
    A None value means the component was excluded (never assumed)."""
    reasons: list[str] = []
    components: dict[str, float | None] = {}

    target_kwp = get_fitness_capacity_adequacy_target_multiple() * get_minimum_viable_kwp()
    components["capacity_adequacy"] = (
        _clamp01(capacity.recommended_kwp / target_kwp) if target_kwp > 0 else 0.0
    )

    headroom_norm = get_fitness_headroom_normalization_kwp()
    components["constraint_headroom"] = (
        _clamp01(capacity.headroom_kwp / headroom_norm) if headroom_norm > 0 else 0.0
    )

    components["geometry_quality"] = _clamp01(site.geometry_confidence)

    shading = site.shading
    if shading is not None and shading.source == "solar_api" and shading.shading_score is not None:
        components["shading"] = _clamp01(shading.shading_score)
    else:
        components["shading"] = None
        reasons.append(
            "Shading data unavailable (non-Solar-API geometry source) — "
            "excluded from score, not assumed zero or full shading."
        )

    performance_ratio = (generation or {}).get("performance_ratio")
    if performance_ratio is not None:
        components["generation_yield"] = _clamp01(performance_ratio)
    else:
        components["generation_yield"] = None
        reasons.append("Detailed generation estimate unavailable — excluded from score.")

    return components, reasons


def _redistributed_weights(components: dict[str, float | None]) -> dict[str, float]:
    """FIT-01/SHADE-04. Weight for an excluded (None) component is
    redistributed proportionally across the components that are present,
    never left implicit as zero."""
    base_weights = get_fitness_weights()
    present = {name: w for name, w in base_weights.items() if components.get(name) is not None}
    total_present_weight = sum(present.values())
    if total_present_weight <= 0:
        return dict.fromkeys(base_weights, 0.0)
    return {name: w / total_present_weight for name, w in present.items()}


def _verdict_from_score(raw_score: float) -> FitnessVerdict:
    """FIT-02."""
    thresholds = get_fitness_verdict_thresholds()
    if raw_score >= thresholds["suitable"]:
        return "SUITABLE"
    if raw_score >= thresholds["suitable_subject_to_survey"]:
        return "SUITABLE_SUBJECT_TO_SURVEY"
    if raw_score >= thresholds["conditional"]:
        return "CONDITIONAL"
    return "NOT_SUITABLE"


def _compute_confidence(
    site: Site,
    capacity: CapacityResult,
    gates: list[Gate],
    calibration_state: float | None,
    *,
    degraded: bool,
) -> float:
    """FIT-04. Never returns exactly 0 — even an INSUFFICIENT_DATA result
    ships a real (if low) confidence figure, per FIT-06."""
    weights = get_fitness_confidence_weights()

    geometry = site.geometry_confidence if site.geometry_confidence is not None else 0.0
    imagery_recency = _imagery_recency_score(site.imagery_date)

    ceilings = capacity.ceilings or []
    constraint_completeness = (
        sum(1 for c in ceilings if c.status == "ok") / len(ceilings) if ceilings else 0.0
    )

    if gates:
        pending_fraction = sum(1 for g in gates if g.status == "PENDING") / len(gates)
        gate_resolution = _clamp01(1.0 - 0.5 * pending_fraction)
    else:
        gate_resolution = 1.0

    calibration = calibration_state if calibration_state is not None else 0.5  # no data yet -> neutral

    blend = (
        weights["geometry"] * geometry
        + weights["imagery_recency"] * imagery_recency
        + weights["constraint_completeness"] * constraint_completeness
        + weights["gate_resolution"] * gate_resolution
        + weights["calibration_state"] * calibration
    )

    confidence_delta = sum(c.confidence_delta for c in ceilings)
    confidence = _clamp01(blend + confidence_delta, floor=0.05)

    if degraded:
        confidence = min(confidence, 0.35)

    return confidence


def _imagery_recency_score(imagery_date: datetime | None) -> float:
    if imagery_date is None:
        return 0.0
    aware_date = imagery_date if imagery_date.tzinfo else imagery_date.replace(tzinfo=UTC)
    age_days = max((datetime.now(UTC) - aware_date).days, 0)

    full = get_fitness_imagery_recency_full_score_days()
    zero = get_fitness_imagery_recency_zero_score_days()
    if age_days <= full:
        return 1.0
    if age_days >= zero:
        return 0.0
    return 1.0 - (age_days - full) / (zero - full)


def _clamp01(value: float, *, floor: float = 0.0, ceiling: float = 1.0) -> float:
    return max(floor, min(ceiling, value))
