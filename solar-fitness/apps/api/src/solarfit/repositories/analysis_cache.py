"""STUB — Owner: Person 3 (AI Pipeline & Cache).

Implements §9.14 Result Cache (CACHE-01..05) of
Solar_Fitness_Engine_Development_Document_v1.1 and the
get_or_create_analysis() lookup-or-compute pattern from §12.1.

  CACHE-01  Key on lat/long rounded via
            solarfit.packs.config_pack.get_cache_precision() — not on
            site id, tenant id, or a provider-specific building id.
  CACHE-02  Look up the cache before invoking any GEO/VIS/weather/VIZ/ML
            step; on a hit, zero external calls.
  CACHE-03  One table, one key scheme, independent of site type.
  CACHE-04  Reuse is unconditional by default — no automatic expiry —
            but an explicit admin "force refresh" path must exist.
  CACHE-05  Every cache hit recorded as such (reused_from_analysis_id +
            timestamps) — never indistinguishable from a fresh run.

First task: write the Alembic migration for `site_analysis_cache`
(lat_rounded, lng_rounded, boundary, vision_refinement jsonb,
weather_snapshot jsonb, panorama_url, ml_suitability_score,
ml_model_version, created_at, last_reused_at), unique index on
(lat_rounded, lng_rounded) — see §14 for the exact DDL. Add it as
migration 0002 (or later, if Person 1's sites table lands first as
0002 — check before numbering).

OBS-09 note: the `vision_refinement` jsonb column must persist the FULL
obstacle list (every detection, applied or not), not just the ones
OBS-04 auto-applied — that raw record is what CAL-style accuracy
reporting compares against once field-survey ground truth exists.
Don't slim it down to "applied obstacles only."

Depends on: solarfit.domain.assessment.AnalysisResult (frozen, Day 0),
solarfit.packs.config_pack.get_cache_precision (frozen loader, Day 0).
"""

from solarfit.domain.assessment import AnalysisResult
from solarfit.packs.config_pack import get_cache_precision


def round_latlng(lat: float, lng: float, precision: int | None = None) -> tuple[float, float]:
    """CACHE-01. precision defaults to the config-pack value if not given."""
    p = precision if precision is not None else get_cache_precision()
    return round(lat, p), round(lng, p)


def find_by_key(lat_rounded: float, lng_rounded: float) -> AnalysisResult | None:
    """Raises NotImplementedError until Person 3 implements it."""
    raise NotImplementedError


def create(**kwargs) -> AnalysisResult:
    """Raises NotImplementedError until Person 3 implements it."""
    raise NotImplementedError


def mark_reused(analysis_id: str) -> None:
    """CACHE-05. Raises NotImplementedError until Person 3 implements it."""
    raise NotImplementedError


def get_or_create_analysis(lat: float, lng: float, site_type: str, params: dict) -> AnalysisResult:
    """CACHE-02/03. See §12.1 for the full reference implementation —
    the cache-hit short-circuit, then the geometry -> vision -> weather
    -> panorama -> ml chain on a miss. Raises NotImplementedError until
    Person 3 implements it."""
    raise NotImplementedError
