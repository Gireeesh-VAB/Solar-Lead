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

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

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


# "customer_marked" is not a detector at all — it's the homeowner
# pointing at their own roof and saying "the water tank is here". It
# rides the same Obstacle model and the same OBS-04 apply path (see
# routers/app_checks.py::mark_check_obstacle) precisely because
# apply/reject are generic over `source`; nothing downstream branches
# on it, it exists so the data model can tell a human's statement apart
# from a machine's inference.
ObstacleSource = Literal["vision_llm", "cv_detector", "customer_marked"]


class Obstacle(BaseModel):
    """OBS-01/02. One detection from the structured-output extension of
    the same vision-LLM call used for VisionRefinement (OBS-01 — never a
    second crop, never a second call), OR (Phase 7) from a separate,
    independently-pluggable detector — see providers/obstacle_detectors.py.

    engine/obstacles.py's apply_or_flag()/reject_applied_obstacle() and
    the persistence layer (repositories/sites.py) are already generic
    over this whole model and need no changes to accept a `source` other
    than "vision_llm" — `source` exists purely so a caller/UI can tell
    detections apart, not because downstream logic branches on it."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))  # stable handle for OBS-06 rejection
    type: ObstacleType
    bounding_polygon: dict  # GeoJSON Polygon, validated per OBS-03 (GEO-07/08 rules)
    confidence: float
    applied: bool = False  # True once OBS-04 has unioned this into exclusions
    # Defaults to the only detector that has ever produced an Obstacle in
    # this codebase — additive, so every obstacle persisted before Phase 7
    # still deserializes correctly.
    source: ObstacleSource = "vision_llm"


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


class SceneMesh(BaseModel):
    """One named part of a client-rendered 3D scene: plain vertex/face
    arrays in the same local metric frame engine/panorama.py builds for
    the .glb export (x east, y north, z up, metres, ground rebased to
    z=0) — so a Three.js BufferGeometry can consume them directly with
    no further projection. Not the .glb pipeline's own trimesh/glTF
    objects: this is the same geometry, serialized as JSON instead of a
    binary scene, for engine/panorama.py::build_scene_geometry()."""

    vertices: list[list[float]]  # [[x, y, z], ...] metres
    faces: list[list[int]]  # [[i, j, k], ...] indices into vertices
    # Per-vertex RGB, 0..1, same order as `vertices` — carries the roof's
    # sunshine-tint heatmap (_vertex_colors_from_segments()) and the panel
    # array's frame/glass colouring. None where the source trimesh mesh
    # was never vertex-coloured (walls, ground, a roof/panels with no
    # usable Building Insights data to tint from).
    colors: list[list[float]] | None = None


class SceneObstacle(BaseModel):
    """One OBS-04 applied obstacle, extruded to a box for the scene
    prototype. `mesh`'s footprint (x/y) is the obstacle's own real
    bounding_polygon — only its extrusion height is a configured
    presentation default (see panorama.py::_OBSTACLE_HEIGHT_M): OBS
    detection carries no measured height, and inventing one per-obstacle
    would misrepresent it as real data."""

    id: str
    type: str | None = None
    mesh: SceneMesh


class SceneGeometryResult(BaseModel):
    """Prototype output of build_scene_geometry() — the roof + walls
    parts of the same real-DSM/segment-plane geometry generate_panorama()
    bakes into a .glb, plus this app's own packed panel array
    (Assessment.panel_layout — NOT Google's solarPanels[], see
    _panel_mesh_from_layout()'s docstring) and OBS-04's applied
    obstacles, returned as JSON for a client-side Three.js viewer
    instead. Additive and read-only: never persisted, never touches
    PanoramaResult or the .glb pipeline."""

    status: Literal["ok", "not_generated"] = "ok"
    reason: str | None = None
    origin_lat: float | None = None
    origin_lng: float | None = None
    height_m: float | None = None
    ground_source: Literal["measured", "fallback"] | None = None
    roof: SceneMesh | None = None
    walls: SceneMesh | None = None
    panels: SceneMesh | None = None
    # Visual-only support-leg/rack geometry under flat-roof-mounted panels
    # (engine/panorama.py::_mounting_leg_mesh()) — never affects panel
    # count, position or tilt, purely presentation.
    mounting: SceneMesh | None = None
    panel_count: int = 0
    obstacles: list[SceneObstacle] = []
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


FitnessVerdict = Literal[
    "SUITABLE",
    "SUITABLE_SUBJECT_TO_SURVEY",
    "CONDITIONAL",
    "INSUFFICIENT_DATA",
    "NOT_SUITABLE",
]


# Phase 6 — "explicit error-condition handling... as first-class, tested
# states". Before this, every failure/warning reason in this pipeline was
# one of three disconnected free-text mechanisms: GeometryRejected's
# exception message, routers/assessments.py::_building_match_warning()'s
# canned sentence, or FitnessResult.binding_constraint's ad hoc
# "insufficient_data:<x>" / "gate:<name>" string prefixes — none
# discriminable by a caller without string-matching. This does NOT
# replace or rename FitnessVerdict (SUITABLE/.../NOT_SUITABLE already is
# a complete, tested, five-state feasibility enum — renaming it would be
# a breaking change to every stored assessment row and both frontends
# for no behavioural gain). Conditions are additive: zero, one, or many
# can accompany any verdict, naming SPECIFIC reasons a verdict landed
# where it did, in a form a caller can branch on instead of re-parsing
# `reasons` sentences.
ConditionCode = Literal[
    "WRONG_BUILDING_RETURNED",
    "NO_SOLAR_API_COVERAGE",
    "HIGH_SHADING",
    "SHADING_DATA_UNAVAILABLE",
    "MISSING_CAPACITY_DATA",
    "MISSING_GEOMETRY_CONFIDENCE",
    "GATE_FAILED",
    "GATE_PENDING",
]


class Condition(BaseModel):
    code: ConditionCode
    message: str
    # The gate's own name (Gate.gate), only present for GATE_FAILED/
    # GATE_PENDING — every other code is a fixed, singleton concept with
    # nothing further to disambiguate.
    detail: str | None = None


class FitnessResult(BaseModel):
    """§9.7 Fitness Scoring (FIT-01..07) + the scoring half of §9.17
    Shading Analysis (SHADE-04). Owner: Person 4, engine/fitness.py.

    This is the SOLE authoritative, reproducible verdict (FIT-06, §17) —
    engine/ml_score.py's MLScore is additive metadata only and must never
    substitute for this. Never constructed without confidence and
    binding_constraint (FIT-06): binding_constraint is always a non-null
    string, using an "insufficient_data:<input>" sentinel naming the
    specific missing mandatory input when verdict == INSUFFICIENT_DATA.
    score is None if and only if verdict == INSUFFICIENT_DATA (FIT-03
    precedence — never a low score standing in for missing data, §17).
    """

    verdict: FitnessVerdict
    score: float | None = None
    confidence: float
    # FIT-04 explainability — the real per-factor values blended into
    # `confidence` above (geometry, imagery_recency, constraint_completeness,
    # gate_resolution, calibration_state, ceiling_delta), plus a
    # deterministic, template-generated explanation of them (see
    # engine/fitness.py::_explain_confidence()). Index 0 of
    # confidence_explanation is always the overall summary sentence;
    # the rest are one sentence per factor, ordered by contribution.
    confidence_components: dict[str, float] = {}
    confidence_explanation: list[str] = []
    binding_constraint: str
    components: dict[str, float | None] = {}
    reasons: list[str] = []
    # Phase 6 — see ConditionCode's docstring above. Populated from
    # WITHIN score_fitness() for anything it itself detects
    # (missing-data reasons, gates, high shading); routers/assessments.py
    # appends WRONG_BUILDING_RETURNED/NO_SOLAR_API_COVERAGE afterward,
    # since those are detected outside this function's own inputs.
    conditions: list[Condition] = []
    limitations: str
    pack_version: str
