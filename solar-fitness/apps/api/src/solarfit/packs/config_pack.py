"""Shared foundation piece — built Day 0 so nobody blocks on Person 2.

CFG-01: every coefficient lives in a versioned YAML parameter pack, never
as a hard-coded constant. This module is the one place that reads those
files. Person 2 owns tuning packages/config-packs/rooftop_v1.yaml to real
values (§9.10 Configuration); Person 1 and Person 3 both read specific
keys from it early (AREA-05's utilisation_factor, CACHE-01's
cache_precision) via the typed accessors below rather than touching YAML
directly.
"""

import os
from functools import lru_cache
from pathlib import Path

import yaml

from solarfit.domain.site import RoofSiteType

# solar-fitness/packages/config-packs, resolved relative to this file so
# it works regardless of the working directory the process is started
# from. Override with SOLARFIT_CONFIG_PACKS_DIR (used by tests).
_DEFAULT_PACKS_DIR = Path(__file__).resolve().parents[5] / "packages" / "config-packs"


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


def get_vision_min_confidence(*, pack: str = "rooftop_v1") -> float:
    """VIS-04. Below this self-reported confidence, treat a vision
    refinement as insufficient_data rather than trusting it."""
    return float(load_pack(pack)["vision_min_confidence"])


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
    recency scores 0.0."""
    return int(load_pack(pack)["fitness_imagery_recency_zero_score_days"])


def get_calibration_variance_threshold(*, pack: str = "rooftop_v1") -> float:
    """CAL-02. Fractional variance above which a calibration record is
    flagged and the remote estimate marked superseded."""
    return float(load_pack(pack)["calibration_variance_threshold"])


def get_calibration_sample_count_threshold(*, pack: str = "rooftop_v1") -> int:
    """CAL-03. Minimum labelled-record count for a site_type before a
    utilisation-factor update is proposed for approval."""
    return int(load_pack(pack)["calibration_sample_count_threshold"])


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
