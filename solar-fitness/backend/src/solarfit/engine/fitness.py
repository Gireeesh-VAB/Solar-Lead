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
          completeness, gate resolution, calibration state. Geometry
          confidence is area-weighted across every real per-plane roof
          segment when Building Insights segment data is available (see
          _aggregate_geometry_confidence()), not just one primary/first
          roof — falls back to the site's own single geometry_confidence
          scalar otherwise. This is entirely separate from FIT-01's own
          `geometry_quality` score component, which is untouched.
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
from itertools import pairwise

from solarfit.domain.assessment import Condition, FitnessResult, FitnessVerdict
from solarfit.domain.constraint import CapacityResult, Gate
from solarfit.domain.site import Site
from solarfit.packs.config_pack import (
    get_fitness_capacity_adequacy_target_multiple,
    get_fitness_confidence_weights,
    get_fitness_headroom_normalization_kwp,
    get_fitness_high_shading_threshold,
    get_fitness_imagery_recency_floor_score,
    get_fitness_imagery_recency_full_score_days,
    get_fitness_imagery_recency_intermediate_points,
    get_fitness_imagery_recency_zero_score_days,
    get_fitness_verdict_thresholds,
    get_fitness_weights,
    get_minimum_viable_kwp,
    pack_version,
)
from solarfit.providers.validation import geometry_confidence as _segment_geometry_confidence

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
      roof_segments: dict | None      — routers/assessments.py::_pack_panel_layout()'s
                                         real per-plane roofSegmentStats (FIT-04 only,
                                         see _aggregate_geometry_confidence() — never
                                         read by _compute_components(), so this can
                                         never move the FIT-01 suitability score)
    """
    params = params or {}
    gates: list[Gate] = params.get("gates", [])
    generation: dict | None = params.get("generation")
    calibration_state: float | None = params.get("calibration_state")
    roof_segments: dict | None = params.get("roof_segments")

    pv = pack_version()

    insufficient_reason = _insufficient_data_reason(site, capacity)
    if insufficient_reason is not None:
        confidence, confidence_components = _compute_confidence(
            site, capacity, gates, calibration_state, roof_segments, degraded=True
        )
        confidence_explanation, confidence_summary = _explain_confidence(confidence_components)
        condition_code = (
            "MISSING_CAPACITY_DATA" if insufficient_reason == "capacity" else "MISSING_GEOMETRY_CONFIDENCE"
        )
        return FitnessResult(
            verdict="INSUFFICIENT_DATA",
            score=None,
            confidence=confidence,
            confidence_components=confidence_components,
            confidence_explanation=[confidence_summary, *confidence_explanation],
            binding_constraint=f"insufficient_data:{insufficient_reason}",
            components={},
            reasons=[f"Insufficient data: {insufficient_reason} missing or unresolved."],
            conditions=[
                Condition(
                    code=condition_code,
                    message=f"Insufficient data: {insufficient_reason} missing or unresolved.",
                )
            ],
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

    confidence, confidence_components = _compute_confidence(
        site, capacity, gates, calibration_state, roof_segments, degraded=False
    )
    confidence_explanation, confidence_summary = _explain_confidence(confidence_components)

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

    conditions: list[Condition] = []
    if fail_gate is not None:
        conditions.append(Condition(code="GATE_FAILED", message=fail_gate.detail, detail=fail_gate.gate))
    for gate in gates:
        if gate.status == "PENDING":
            conditions.append(Condition(code="GATE_PENDING", message=gate.detail, detail=gate.gate))
    shading_score = components.get("shading")
    if shading_score is None:
        conditions.append(
            Condition(
                code="SHADING_DATA_UNAVAILABLE",
                message="Shading data unavailable (non-Solar-API geometry source) — excluded from score.",
            )
        )
    elif shading_score <= get_fitness_high_shading_threshold():
        conditions.append(
            Condition(
                code="HIGH_SHADING",
                message=f"This roof's shading component scored {shading_score:.2f} — meaningfully less sun than an unobstructed roof.",
            )
        )

    return FitnessResult(
        verdict=verdict,
        score=round(raw_score, 4),
        confidence=confidence,
        confidence_components=confidence_components,
        confidence_explanation=[confidence_summary, *confidence_explanation],
        binding_constraint=binding_constraint,
        components=components,
        reasons=reasons,
        conditions=conditions,
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
    roof_segments: dict | None = None,
    *,
    degraded: bool,
) -> tuple[float, dict[str, float]]:
    """FIT-04. Never returns exactly 0 — even an INSUFFICIENT_DATA result
    ships a real (if low) confidence figure, per FIT-06.

    Also returns the raw per-factor values that were blended into the
    final figure (FIT-04 explainability) — real numbers, computed here
    and otherwise discarded, never a fabricated breakdown reverse-
    engineered from the blend."""
    weights = get_fitness_confidence_weights()

    geometry = _aggregate_geometry_confidence(site, roof_segments)
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

    components = {
        "geometry": geometry,
        "imagery_recency": imagery_recency,
        "constraint_completeness": constraint_completeness,
        "gate_resolution": gate_resolution,
        "calibration_state": calibration,
        "ceiling_delta": confidence_delta,
    }

    return confidence, components


_CONFIDENCE_FACTOR_LABELS: dict[str, str] = {
    "geometry": "Roof boundary and geometry data",
    "imagery_recency": "Imagery recency",
    "constraint_completeness": "Constraint data completeness",
    "gate_resolution": "Site-check resolution",
    "calibration_state": "Field-calibration accuracy",
}


def _confidence_tier_phrase(value: float) -> str:
    if value >= 0.8:
        return "this strengthened the result"
    if value <= 0.5:
        return "this held the result back"
    return "this was a moderate factor"


def _explain_confidence(components: dict[str, float]) -> tuple[list[str], str]:
    """FIT-04 explainability. Deterministic, template-based: every
    sentence is derived straight from the same numbers that produced the
    blended confidence figure (see _compute_confidence() above) — never
    free-form/generated text, so the same inputs always produce the same
    explanation (FIT-06)."""
    weights = get_fitness_confidence_weights()
    contributions = [
        (name, components[name], weights.get(name, 0.0) * components[name])
        for name in _CONFIDENCE_FACTOR_LABELS
        if name in components
    ]
    contributions.sort(key=lambda item: item[2], reverse=True)

    factor_sentences = [
        f"{_CONFIDENCE_FACTOR_LABELS[name]} scored {value * 100:.0f}%, contributing "
        f"{weighted * 100:.0f} points toward the total — {_confidence_tier_phrase(value)}."
        for name, value, weighted in contributions
    ]

    ceiling_delta = components.get("ceiling_delta", 0.0)
    if abs(ceiling_delta) >= 0.01:
        direction = "raised" if ceiling_delta > 0 else "lowered"
        factor_sentences.append(
            f"Constraint-specific adjustments {direction} confidence by {abs(ceiling_delta) * 100:.0f} points."
        )

    if not contributions:
        return factor_sentences, "Confidence could not be broken down into factors for this assessment."

    best_name, best_value, _ = contributions[0]
    worst_name, worst_value, _ = contributions[-1]
    if best_name != worst_name:
        summary = (
            f"Confidence was driven mainly by {_CONFIDENCE_FACTOR_LABELS[best_name].lower()} "
            f"({best_value * 100:.0f}%); the main thing holding it back was "
            f"{_CONFIDENCE_FACTOR_LABELS[worst_name].lower()} ({worst_value * 100:.0f}%)."
        )
    else:
        summary = (
            f"Confidence was driven by {_CONFIDENCE_FACTOR_LABELS[best_name].lower()} "
            f"({best_value * 100:.0f}%)."
        )

    return factor_sentences, summary


def _aggregate_geometry_confidence(site: Site, roof_segments: dict | None) -> float:
    """FIT-04/GEO-09. Real per-roof geometry confidence, area-weighted,
    for the CONFIDENCE blend ONLY.

    Deliberately never touches `_compute_components()`'s own
    `geometry_quality` (a FIT-01 SCORE input), which keeps reading the
    single stored `site.geometry_confidence` scalar completely unchanged
    — so this function can never move the suitability score, only the
    confidence figure.

    "Multiple roofs" in this codebase means Building Insights' real
    per-plane data (`roof_segments["segments"]`, built by
    routers/assessments.py::_pack_panel_layout()) WITHIN one site
    boundary — there is no independent-polygon-per-site data model
    (domain/site.py's `Site.boundary` is a single Polygon, and
    providers/validation.py::validate_boundary() rejects anything else).
    Every segment shares the site's own `geometry_source` and
    `imagery_date` (one Solar API capture for the whole building — there
    is no per-segment provenance or imagery date anywhere to preserve),
    so only each segment's OWN polygon (vertex count, area) varies
    providers/validation.py::geometry_confidence()'s output between
    segments; imagery recency itself stays the single site-level
    computation in `_compute_confidence()` for exactly this reason.

    Weighted by `overlapAreaM2` — each segment's area actually clipped
    to the customer's own resolved/selected boundary (routers/
    assessments.py::_pack_panel_layout()'s `_segment_polygon_metric()`
    intersection), never by the segment's raw, un-clipped Google area.
    A segment with zero overlap with what the customer selected (a
    neighbouring plane, a wing of the building they didn't crop in) is
    excluded from the aggregate entirely — it must not pull this site's
    confidence at all, let alone at full weight, since it isn't part of
    the roof the customer actually selected. A segment that only
    partially overlaps counts only by that overlapping portion.

    Falls back to the existing single `site.geometry_confidence` scalar
    verbatim when there's nothing to aggregate (no Building Insights
    segments at all, or none overlap the selected boundary — manual/
    imported/field_measured sites, or a Building Insights outage) —
    every such site's confidence is byte-identical to before this
    function existed.
    """
    site_level = site.geometry_confidence if site.geometry_confidence is not None else 0.0
    segments = (roof_segments or {}).get("segments") or []
    if not segments:
        return site_level

    weighted_sum = 0.0
    total_weight = 0.0
    for segment in segments:
        overlap_area = segment.get("overlapAreaM2")
        if not overlap_area or overlap_area <= 0:
            # No real overlap with the customer's own selected/cropped
            # area — this Google segment isn't part of what they
            # selected, so it must not stand in for it here.
            continue
        polygon = segment.get("polygon")
        confidence = (
            _segment_geometry_confidence(
                source=site.geometry_source,
                imagery_date=site.imagery_date,
                # routers/assessments.py::_metric_polygon_to_wgs84_ring()
                # returns a bare exterior ring (list[[lng, lat], ...]),
                # not a GeoJSON dict — geometry_confidence() needs the
                # latter to shape() it.
                boundary={"type": "Polygon", "coordinates": [polygon]},
            )
            if polygon is not None
            else site_level
        )
        weighted_sum += confidence * overlap_area
        total_weight += overlap_area

    if total_weight <= 0:
        return site_level
    return _clamp01(weighted_sum / total_weight)


def _imagery_recency_score(imagery_date: datetime | None) -> float:
    """FIT-04 imagery_recency sub-component. Missing imagery date is the
    existing, unchanged fallback — 0.0, never a guessed/invented date
    (see FIT-06's "never assume" discipline elsewhere in this module).

    Otherwise: 1.0 at/below full_score_days, then a piecewise-linear
    step-down through the pack's own intermediate (age_days, score)
    points, holding at floor_score beyond zero_score_days — old imagery
    still costs confidence, but never enough on its own to read as "no
    confidence at all" the way decaying all the way to 0.0 did.
    """
    if imagery_date is None:
        return 0.0
    aware_date = imagery_date if imagery_date.tzinfo else imagery_date.replace(tzinfo=UTC)
    age_days = max((datetime.now(UTC) - aware_date).days, 0)

    full = get_fitness_imagery_recency_full_score_days()
    zero = get_fitness_imagery_recency_zero_score_days()
    floor = get_fitness_imagery_recency_floor_score()
    breakpoints = [
        (full, 1.0),
        *get_fitness_imagery_recency_intermediate_points(),
        (zero, floor),
    ]
    return _piecewise_linear(age_days, breakpoints, floor=floor)


def _piecewise_linear(x: float, points: list[tuple[float, float]], *, floor: float) -> float:
    """Linear interpolation through `points` (sorted ascending by x):
    flat at the first point's y for any x at/below it, a straight-line
    segment between each consecutive pair, and `floor` beyond the last
    point's x. Generic — not specific to imagery dates or any other
    single caller."""
    first_x, first_y = points[0]
    if x <= first_x:
        return first_y
    for (x0, y0), (x1, y1) in pairwise(points):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return floor


def _clamp01(value: float, *, floor: float = 0.0, ceiling: float = 1.0) -> float:
    return max(floor, min(ceiling, value))
