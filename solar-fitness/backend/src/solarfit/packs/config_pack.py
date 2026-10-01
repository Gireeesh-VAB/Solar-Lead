"""Shared foundation piece — built Day 0 so nobody blocks on Person 2.

CFG-01: every coefficient lives in a versioned YAML parameter pack, never
as a hard-coded constant. This module is the one place that reads those
files. Person 2 owns tuning packages/config-packs/rooftop_v1.yaml to real
values (§9.10 Configuration); Person 1 and Person 3 both read specific
keys from it early (AREA-05's utilisation_factor, CACHE-01's
cache_precision) via the typed accessors below rather than touching YAML
directly.

CFG-02 (version stamping) and CFG-03 (reproducibility): pack_version()
below is what gets stamped on a stored result, and
tests/test_resolver.py's purity test plus test_generation.py demonstrate
that resolve_capacity()/estimate_generation_kwh() are deterministic given
the same inputs and pack version — the two things Person 2 can prove in
isolation. CFG-04 (bulk recompute after a pack change) and CFG-05
(tenant-scoped overrides) both require a stored-assessment
repository/tenant model that doesn't exist yet anywhere in the codebase
(Person 1/Person 3's repositories are still stubs) — flagged to the team
as blocked on that landing first, rather than built against
infrastructure that isn't there.
"""

import os
from functools import lru_cache
from pathlib import Path

import yaml

from solarfit.domain.site import RoofSiteType

# solar-fitness/backend/packages/config-packs, resolved relative to
# this file so it works regardless of the working directory the
# process is started from. Override with SOLARFIT_CONFIG_PACKS_DIR
# (used by tests).
_DEFAULT_PACKS_DIR = Path(__file__).resolve().parents[3] / "packages" / "config-packs"


def _packs_dir() -> Path:
    override = os.environ.get("SOLARFIT_CONFIG_PACKS_DIR")
    return Path(override) if override else _DEFAULT_PACKS_DIR


@lru_cache
def load_pack(name: str = "rooftop_v1") -> dict:
    """Load and cache a named parameter pack, e.g. load_pack('rooftop_v1')."""
    path = _packs_dir() / f"{name}.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_utilisation_factor(site_type: RoofSiteType, *, pack: str = "rooftop_v1") -> float:
    """AREA-05. Raises KeyError if the pack has no entry for site_type —
    callers should let AREA-05's INSUFFICIENT_DATA-style handling apply,
    never silently default to a made-up number."""
    return load_pack(pack)["utilisation_factor"][site_type]


def get_cache_precision(*, pack: str = "rooftop_v1") -> int:
    """CACHE-01. Decimal places to round latitude/longitude to for the
    result-cache key."""
    return int(load_pack(pack)["cache_precision"])


def get_edge_setback_m(*, pack: str = "rooftop_v1") -> float:
    """AREA-03."""
    return float(load_pack(pack)["edge_setback_m"])


def get_parapet_setback_m(*, pack: str = "rooftop_v1") -> float:
    """AREA-03's sibling coefficient. Stacks with edge_setback_m as one
    combined inward buffer on the boundary — see engine/area.py's own
    docstring for why this is a documented simplification (uniform
    across the whole roof) rather than a claim of per-edge parapet
    detection: nothing in this pipeline's real data sources (Building
    Insights, the mask, DSM-as-used-today) reports where a parapet wall
    actually stands."""
    return float(load_pack(pack)["parapet_setback_m"])


def get_obstacle_setback_m(*, pack: str = "rooftop_v1") -> float:
    """A real, physical clearance around each detected obstacle — a
    panel installed flush against a water tank's base is not
    installable in practice. Distinct from edge_setback_m/
    parapet_setback_m (which act on the roof boundary): this buffers
    OUT each exclusion polygon before it's subtracted, so panels keep
    clear of obstacle edges too, not just their exact footprint."""
    return float(load_pack(pack)["obstacle_setback_m"])


def get_minimum_viable_kwp(*, pack: str = "rooftop_v1") -> float:
    """CON-07."""
    return float(load_pack(pack)["minimum_viable_kwp"])


def get_auto_apply_confidence_threshold(*, pack: str = "rooftop_v1") -> float:
    """OBS-04. Obstacle detections at or above this confidence auto-apply
    to exclusions; below it, they stay advisory-only (OBS-05)."""
    return float(load_pack(pack)["auto_apply_confidence_threshold"])


def get_shading_derate_factor(*, pack: str = "rooftop_v1") -> float:
    """SHADE-03."""
    return float(load_pack(pack)["shading_derate_factor"])


def get_pvgis_system_loss_pct(*, pack: str = "rooftop_v1") -> float:
    """GEN-04. System loss % passed to PVGIS's PVcalc `loss` param
    (wiring, cabling, soiling, etc. — separate from the shading derate
    above). 14% is PVGIS's own conventional default."""
    return float(load_pack(pack)["pvgis_system_loss_pct"])


def get_vision_min_confidence(*, pack: str = "rooftop_v1") -> float:
    """VIS-04. Below this self-reported confidence, treat a vision
    refinement as insufficient_data rather than trusting it."""
    return float(load_pack(pack)["vision_min_confidence"])


def get_max_centroid_distance_m(*, pack: str = "rooftop_v1") -> float:
    """GEO-07. A boundary this far from the site's own centroid means the
    geocode and the trace disagree about which building this is."""
    return float(load_pack(pack)["max_centroid_distance_m"])


def get_min_plausible_boundary_area_m2(*, pack: str = "rooftop_v1") -> float:
    """GEO-07. Below this, a boundary is a units error or a mis-traced
    sliver, not a roof."""
    return float(load_pack(pack)["min_plausible_boundary_area_m2"])


def get_max_plausible_boundary_area_m2(*, pack: str = "rooftop_v1") -> float:
    """GEO-07. Above this, a boundary is a mis-traced neighbourhood, not
    a roof — deliberately wide, this rejects nonsense rather than
    second-guessing a genuinely large industrial roof."""
    return float(load_pack(pack)["max_plausible_boundary_area_m2"])


def get_min_obstacle_area_m2(*, pack: str = "rooftop_v1") -> float:
    """OBS-03/GEO-07. An obstacle's geodesic area must be at least this
    large (m^2) to be plausible."""
    return float(load_pack(pack)["min_obstacle_area_m2"])


def get_max_obstacle_area_fraction_of_boundary(*, pack: str = "rooftop_v1") -> float:
    """OBS-03/GEO-07. Above this fraction of the boundary's own area, an
    obstacle is implausibly large to be real."""
    return float(load_pack(pack)["max_obstacle_area_fraction_of_boundary"])


def get_panorama_grid_resolution(*, pack: str = "rooftop_v1") -> int:
    """VIZ-01. Points per side of the elevation grid sampled from the DSM
    crop before triangulation."""
    return int(load_pack(pack)["panorama_grid_resolution"])


def get_panorama_enabled(*, pack: str = "rooftop_v1") -> bool:
    """VIZ-05. Whether to generate a .glb at all — see the pack's note."""
    return bool(load_pack(pack)["panorama_enabled"])


def get_panorama_build_params(*, pack: str = "rooftop_v1") -> dict[str, float]:
    """VIZ-01. The 3D building-assembly tunables — ground estimation,
    height sanity bounds, ground-plane margin, and solar-panel mounting
    geometry. Returned as one dict because engine/panorama.py needs the
    whole set together on every call."""
    data = load_pack(pack)
    return {
        "ground_search_buffer_m": float(data["panorama_ground_search_buffer_m"]),
        "max_roof_step_m": float(data["panorama_max_roof_step_m"]),
        "ground_percentile": float(data["panorama_ground_percentile"]),
        "min_building_height_m": float(data["panorama_min_building_height_m"]),
        "max_building_height_m": float(data["panorama_max_building_height_m"]),
        "fallback_building_height_m": float(data["panorama_fallback_building_height_m"]),
        "ground_margin_m": float(data["panorama_ground_margin_m"]),
        "roof_smoothing_passes": float(data["panorama_roof_smoothing_passes"]),
        "roof_smoothing_weight": float(data["panorama_roof_smoothing_weight"]),
        "panel_thickness_m": float(data["panorama_panel_thickness_m"]),
        "panel_clearance_m": float(data["panorama_panel_clearance_m"]),
        "panel_gap_m": float(data["panorama_panel_gap_m"]),
        "panel_frame_m": float(data["panorama_panel_frame_m"]),
    }


def get_panel_packing_params(*, pack: str = "rooftop_v1") -> dict:
    """Panel-packing geometry — module size, gaps, walkways, tilt.

    Returned whole because the packer needs the entire set together, and
    a half-applied spacing rule is worse than none."""
    return dict(load_pack(pack)["panel_packing"])


def get_roof_mask_params(*, pack: str = "rooftop_v1") -> dict:
    """GEO-04's real-outline upgrade — tuning for vectorising the Solar
    API building mask into a roof polygon (providers/solar_api.py::
    extract_roof_polygon_from_mask). Returned whole for the same reason
    as panel packing above: these values only make sense together."""
    return dict(load_pack(pack)["roof_mask"])


def get_roof_segment_match_tolerance_m(*, pack: str = "rooftop_v1") -> float:
    """GEO-10 — how far (metres) a pin may sit outside a Solar API roof
    segment's own boundingBox and still count as a genuine match
    (providers/solar_api.py::match_roof_segment)."""
    return float(load_pack(pack)["roof_segment_match_tolerance_m"])


def get_capacity_density_kwp_per_m2(*, pack: str = "rooftop_v1") -> float:
    """CON-07/universal.py's area-to-kWp conversion for the usable-area
    ceiling and the minimum-viable-size gate."""
    return float(load_pack(pack)["capacity_density_kwp_per_m2"])


def get_net_metering_export_ratio(*, pack: str = "rooftop_v1") -> float:
    """CON-05. `pack` lets a jurisdiction override (e.g. 'jurisdictions/in_ap')
    supply its own ratio with no change to the caller (CON-08)."""
    return float(load_pack(pack)["net_metering_cap"]["max_export_ratio_of_sanctioned_load"])


def get_electricity_tariff_inr_per_kwh(*, pack: str = "rooftop_v1") -> float:
    """Effective retail tariff for turning a monthly bill into units.

    A placeholder average, not a slab model — see the pack's own note.
    Every bill-derived system size scales inversely with it."""
    return float(load_pack(pack)["electricity_tariff_inr_per_kwh"])


def get_consumption_offset_target_ratio(*, pack: str = "rooftop_v1") -> float:
    """CON-05."""
    return float(load_pack(pack)["consumption_offset_ceiling"]["target_offset_ratio"])


def get_consumption_offset_assumed_yield(*, pack: str = "rooftop_v1") -> float:
    """CON-05. kWh/kWp/year fallback used only when generation.py hasn't
    produced a real yield figure yet for this site."""
    return float(
        load_pack(pack)["consumption_offset_ceiling"]["assumed_specific_yield_kwh_per_kwp"]
    )


def get_transformer_headroom_max_fraction(*, pack: str = "rooftop_v1") -> float:
    """CON-05."""
    return float(load_pack(pack)["transformer_headroom"]["max_fraction_of_transformer_capacity"])


def get_performance_adjustment(site_type: RoofSiteType, *, pack: str = "rooftop_v1") -> float:
    """GEN-03. Multiplier on the default performance ratio, by site type
    (e.g. floating arrays run cooler than rooftop in the wider engine —
    rooftop-only scope keeps this at 1.0 today, but it must stay
    configurable rather than assumed)."""
    return float(load_pack(pack)["performance_adjustment"][site_type])


def get_default_performance_ratio(*, pack: str = "rooftop_v1") -> float:
    """GEN-01. Baseline performance ratio before the GEN-03 site-type
    adjustment and SHADE-03 shading derate are applied."""
    return float(load_pack(pack)["default_performance_ratio"])


def get_fallback_specific_yield_kwh_per_kwp(*, pack: str = "rooftop_v1") -> float:
    """GEN-01/02. Reference specific yield (kWh/kWp/year) used both as the
    weather-unavailable fallback and as the base the GEN-02 weather
    refinement multiplier scales."""
    return float(load_pack(pack)["fallback_specific_yield_kwh_per_kwp"])


def get_reference_irradiance_w_m2(*, pack: str = "rooftop_v1") -> float:
    """GEN-02. Baseline irradiance the current weather reading is compared
    against to produce the weather-refinement multiplier."""
    return float(load_pack(pack)["reference_irradiance_w_m2"])


def get_weather_refinement_multiplier_bounds(*, pack: str = "rooftop_v1") -> tuple[float, float]:
    """GEN-02. Clamp on the weather-refinement multiplier so a single
    instantaneous reading can't swing the estimate implausibly far from
    the reference yield."""
    low, high = load_pack(pack)["weather_refinement_multiplier_bounds"]
    return float(low), float(high)


def get_subsidy_tier_cap(tier: str, *, pack: str = "rooftop_v1") -> float | None:
    """CON-05. Returns None (not a fabricated number) for a tier the pack
    has no cap for, e.g. 'UNKNOWN' while USN hasn't been captured yet."""
    caps = load_pack(pack)["subsidy_tier_cap"]
    return caps.get(tier)


def get_installation_cost_inr_per_kwp(*, pack: str = "rooftop_v1") -> dict[str, float]:
    """FIN-01. Returned whole, same reasoning as get_panel_packing_params
    above: these line items only make sense summed together against a
    resolved capacity_kwp. An engine ESTIMATE, not a real vendor quote —
    see FinancialFeasibilityOut's docstring."""
    return {k: float(v) for k, v in load_pack(pack)["installation_cost_inr_per_kwp"].items()}


def get_subsidy_scheme(*, pack: str = "rooftop_v1") -> dict:
    """FIN-01. eligible_site_types/inr_per_kwp/max_capacity_kwp/
    max_amount_inr — a central-scheme approximation, not a real
    application outcome."""
    return dict(load_pack(pack)["subsidy_scheme"])


def get_panel_degradation_pct_per_year(*, pack: str = "rooftop_v1") -> float:
    """FIN-01. Applied when projecting 10/20-year savings from the
    current year's annual savings figure."""
    return float(load_pack(pack)["panel_degradation_pct_per_year"])


def get_system_lifetime_years(*, pack: str = "rooftop_v1") -> float:
    """FIN-01."""
    return float(load_pack(pack)["system_lifetime_years"])


def get_async_task_timeout_s(*, pack: str = "rooftop_v1") -> float:
    """VIS-05/VIZ-05/OBS-07. Seconds to wait on `.get()` for a dispatched
    Celery task (vision refinement, obstacle apply, panorama generation)
    before giving up — these run through the real worker/queue
    infrastructure rather than inline, but the calling endpoint is still
    synchronous, so this bounds how long a request can block on a
    worker that's slow or unavailable."""
    return float(load_pack(pack)["async_task_timeout_s"])


def get_vendor_sla_at_risk_window_hours(*, pack: str = "rooftop_v1") -> float:
    """repositories/vendors.py::sweep_vendor_job_sla(). Hours before a
    job's deadline at which an assigned-but-not-yet-submitted job is
    flagged "sla_at_risk" — an early warning, not yet a reassignment."""
    return float(load_pack(pack)["vendor_sla_at_risk_window_hours"])


def get_vendor_lead_reassignment_extension_days(*, pack: str = "rooftop_v1") -> float:
    """repositories/vendors.py::sweep_vendor_job_sla(). Days a
    reassigned lead's fresh deadline is set out from the moment it
    passes to the next eligible vendor — deliberately a SEPARATE
    coefficient from the original ApproveAssessmentRequest.deadline_days
    an admin sets at approval time (that one is the customer-facing
    first offer; this one is how much runway the NEXT vendor in line
    gets, which need not be the same)."""
    return float(load_pack(pack)["vendor_lead_reassignment_extension_days"])


def pack_version(*, pack: str = "rooftop_v1") -> str:
    """CFG-02. Stamped on every stored result alongside the constraint
    pack version."""
    return str(load_pack(pack)["version"])


def get_fitness_weights(*, pack: str = "rooftop_v1") -> dict[str, float]:
    """FIT-01. Component weights for the fitness score, keyed by
    component name. Callers must redistribute weight across present
    components when a degradable one (shading, generation_yield) is
    excluded, rather than assuming it as zero."""
    return dict(load_pack(pack)["fitness_weights"])


def get_fitness_verdict_thresholds(*, pack: str = "rooftop_v1") -> dict[str, float]:
    """FIT-02. Raw-score cutoffs for suitable / suitable_subject_to_survey
    / conditional; below the lowest cutoff is NOT_SUITABLE."""
    return dict(load_pack(pack)["fitness_verdict_thresholds"])


def get_fitness_high_shading_threshold(*, pack: str = "rooftop_v1") -> float:
    """Phase 6 — a `shading` component (0..1, higher = less shaded) at or
    below this raw-score threshold surfaces a HIGH_SHADING condition
    alongside the verdict. Deliberately separate from
    fitness_verdict_thresholds: this doesn't change the verdict itself
    (shading is already folded into raw_score via its own weight) — it's
    an explicit, named flag for a specific reason a borderline verdict
    landed where it did, per Phase 6's "explicit error-condition
    handling" goal."""
    return float(load_pack(pack)["fitness_high_shading_threshold"])


def get_fitness_capacity_adequacy_target_multiple(*, pack: str = "rooftop_v1") -> float:
    """FIT-01 capacity_adequacy component normalisation target."""
    return float(load_pack(pack)["fitness_capacity_adequacy_target_multiple"])


def get_fitness_headroom_normalization_kwp(*, pack: str = "rooftop_v1") -> float:
    """FIT-01 constraint_headroom component normalisation target."""
    return float(load_pack(pack)["fitness_headroom_normalization_kwp"])


def get_fitness_confidence_weights(*, pack: str = "rooftop_v1") -> dict[str, float]:
    """FIT-04. Confidence-blend weights, keyed by sub-input name."""
    return dict(load_pack(pack)["fitness_confidence_weights"])


def get_fitness_imagery_recency_full_score_days(*, pack: str = "rooftop_v1") -> int:
    """FIT-04 imagery_recency sub-component — age in days at/below which
    recency scores 1.0."""
    return int(load_pack(pack)["fitness_imagery_recency_full_score_days"])


def get_fitness_imagery_recency_zero_score_days(*, pack: str = "rooftop_v1") -> int:
    """FIT-04 imagery_recency sub-component — age in days at/above which
    recency reaches its floor score (get_fitness_imagery_recency_floor_
    score() — no longer 0.0; the name predates that floor)."""
    return int(load_pack(pack)["fitness_imagery_recency_zero_score_days"])


def get_fitness_imagery_recency_intermediate_points(
    *, pack: str = "rooftop_v1"
) -> list[tuple[float, float]]:
    """FIT-04 imagery_recency sub-component — (age_days, score) points
    the curve passes through exactly between full_score_days and
    zero_score_days, sorted ascending by age. Lets the decay step down
    in stages instead of one straight line from 1.0 to the floor."""
    return [tuple(point) for point in load_pack(pack)["fitness_imagery_recency_intermediate_points"]]


def get_fitness_imagery_recency_floor_score(*, pack: str = "rooftop_v1") -> float:
    """FIT-04 imagery_recency sub-component — the minimum score old
    imagery can be scored down to, however old it gets. Old imagery
    should still cost confidence, never enough on its own to read as
    "no confidence at all"."""
    return float(load_pack(pack)["fitness_imagery_recency_floor_score"])


def get_calibration_variance_threshold(*, pack: str = "rooftop_v1") -> float:
    """CAL-02. Fractional variance above which a calibration record is
    flagged and the remote estimate marked superseded."""
    return float(load_pack(pack)["calibration_variance_threshold"])


def get_calibration_sample_count_threshold(*, pack: str = "rooftop_v1") -> int:
    """CAL-03. Minimum labelled-record count for a site_type before a
    utilisation-factor update is proposed for approval."""
    return int(load_pack(pack)["calibration_sample_count_threshold"])


def get_utilisation_factor_proposal_bounds(*, pack: str = "rooftop_v1") -> tuple[float, float]:
    """CAL-03. Clamp on a proposed utilisation-factor correction — a
    single batch of field surveys shouldn't be able to propose an
    implausible factor outside this range, whatever the raw median ratio
    says."""
    low, high = load_pack(pack)["utilisation_factor_proposal_bounds"]
    return float(low), float(high)


def get_calibration_confidence_no_data(*, pack: str = "rooftop_v1") -> float:
    """CAL-05. Neutral confidence figure when no calibration records
    exist yet for a site_type/geometry_source — matches engine/
    fitness.py's own "None means neutral" treatment of this input."""
    return float(load_pack(pack)["calibration_confidence_no_data"])


def get_calibration_confidence_high_variance(*, pack: str = "rooftop_v1") -> float:
    """CAL-05. Confidence figure when the mean absolute variance exceeds
    calibration_variance_threshold."""
    return float(load_pack(pack)["calibration_confidence_high_variance"])


def get_calibration_confidence_validated(*, pack: str = "rooftop_v1") -> float:
    """CAL-05. Confidence figure when calibration records exist and
    variance is within threshold."""
    return float(load_pack(pack)["calibration_confidence_validated"])


def get_usn_ocr_retention_days(*, pack: str = "rooftop_v1") -> int:
    """USN-06. Days a bill/payment-proof upload and its raw OCR text are
    retained before the purge job removes them."""
    return int(load_pack(pack)["usn_ocr_retention_days"])


def get_ml_min_training_groups(*, pack: str = "rooftop_v1") -> int:
    """ML-01. Minimum distinct site_id groups before train() attempts
    anything."""
    return int(load_pack(pack)["ml_min_training_groups"])


def get_ml_cv_max_folds(*, pack: str = "rooftop_v1") -> int:
    """ML-01. Cap on cross-validation folds during hyperparameter
    search."""
    return int(load_pack(pack)["ml_cv_max_folds"])


def get_ml_test_split_fraction(*, pack: str = "rooftop_v1") -> float:
    """ML-01. Fraction of site_id groups held out for the final
    promotion-vs-baseline test split."""
    return float(load_pack(pack)["ml_test_split_fraction"])
