"""Shared contract — built Day 0, frozen for the whole team.

Backs §9.7 Fitness Scoring (FIT), §9.11 Vision Refinement (VIS),
§9.12 3D Visualization (VIZ), §9.13 ML Suitability Model (ML),
§9.14 Result Cache (CACHE), and §9.16 Obstacle Detection (OBS) of
Solar_Fitness_Engine_Development_Document_v1.2.

AnalysisResult's vision_refinement / panorama / ml_score / cache_hit
fields are all optional and additive per API-01 — never required, never
displacing the FIT verdict, which stays the sole reproducible,
authoritative output (FIT-06, §17).

Obstacle detection (OBS) is the one exception to "additive only": an
obstacle at or above the configured confidence threshold auto-applies
to the site's exclusions (OBS-04) — but it does so through the same
versioned SITE-05 mechanism as any other boundary change, so it's still
fully auditable and reversible (OBS-06), never a silent overwrite.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from solarfit.domain.constraint import CapacityResult

ObstacleType = Literal[
    "water_tank",
    "hvac_unit",
    "chimney",
    "existing_solar_panel",
    "vent",
    "antenna",
    "other",
]


class Obstacle(BaseModel):
    """OBS-01/02. One detection from the structured-output extension of
    the same vision-LLM call used for VisionRefinement (OBS-01 — never a
    second crop, never a second call)."""

    type: ObstacleType
    bounding_polygon: dict  # GeoJSON Polygon, validated per OBS-03 (GEO-07/08 rules)
    confidence: float
    applied: bool = False  # True once OBS-04 has unioned this into exclusions


class VisionRefinement(BaseModel):
    """VIS-02/03. Inference-time only — never fine-tuning, never stored
    imagery beyond what VIS-06's licensing review permits.

    obstacles (OBS-01) rides the same structured-output call as
    corrected_boundary — see engine/obstacles.py for what happens to
    each detection above/below the confidence threshold.
    """

    corrected_boundary: dict | None = None  # GeoJSON Polygon, a suggestion only
    obstruction_notes: list[str] = []
    obstacles: list[Obstacle] = []
    confidence: float | None = None
    status: Literal["ok", "insufficient_data"] = "ok"


class PanoramaResult(BaseModel):
    """VIZ-02/03. Only a reference URL is persisted — the mesh/render
    artifact itself lives in object storage."""

    url: str | None = None
    status: Literal["ok", "not_generated"] = "ok"
    reason: str | None = None  # required when status == "not_generated"
    generated_at: datetime | None = None
    version: str | None = None


class MLScore(BaseModel):
    """ML-01/02/05. Additive metadata only — see module docstring."""

    score: float | None = None
    model_version: str | None = None
    status: Literal["ok", "insufficient_data"] = "ok"


class AnalysisResult(BaseModel):
    """The shape returned by packs/config_pack-driven pipeline runs and
    cached in site_analysis_cache (CACHE-01..05). Person 3's
    get_or_create_analysis() in repositories/analysis_cache.py returns
    this; Person 4's routers/assessments.py assembles the final API-01
    response around it plus the FIT verdict.
    """

    boundary: dict  # GeoJSON Polygon
    usable_area_m2: float | None = None
    capacity: CapacityResult | None = None

    vision_refinement: VisionRefinement | None = None
    panorama: PanoramaResult | None = None
    ml_score: MLScore | None = None

    cache_hit: bool = False
    reused_from_analysis_id: str | None = None

    engine_version: str | None = None
    constraint_pack_version: str | None = None
