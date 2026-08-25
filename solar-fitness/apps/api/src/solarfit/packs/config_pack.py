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


def pack_version(*, pack: str = "rooftop_v1") -> str:
    """CFG-02. Stamped on every stored result alongside the constraint
    pack version."""
    return str(load_pack(pack)["version"])
