"""STUB — Owner: Person 3 (AI Pipeline & Cache).

Implements §9.11 Vision Refinement (VIS-01..06) AND the detection half
of §9.16 Obstacle Detection (OBS-01..03) of
Solar_Fitness_Engine_Development_Document_v1.2. Crop the provider
boundary, call GPT-4 Vision ONCE for a combined refinement + obstacle
pass, store as a VisionRefinement annotation — NEVER overwrite Person
1's boundary directly here (VIS-03, §17); auto-apply of high-confidence
obstacles is engine/obstacles.py's job (OBS-04..06), not this module's.

  VIS-01  Crop source imagery to the provider-derived boundary first —
          never send an uncropped tile.
  VIS-02  Structured-output prompt to the vision-LLM; parse the response.
  VIS-03  Store as an annotation; never overwrite the provider geometry.
  VIS-04  Failure/low-confidence -> insufficient_data; never block the
          pipeline on this step.
  VIS-05  Run as a Celery task (workers/) — never in the request path.
  VIS-06  retain_imagery flag defaults False; imagery-licensing review
          is an open legal item, not assumed clear.
  OBS-01  Extend VIS-02's SAME call/schema with an `obstacles` field —
          do not crop or call the vision-LLM a second time for this.
  OBS-02  Obstacle types: water_tank, hvac_unit, chimney,
          existing_solar_panel, vent, antenna, other.
  OBS-03  Validate each obstacle's bounding_polygon against GEO-07/08's
          rules (coordinate with Person 1's validation helpers in
          providers/base.py) — drop invalid polygons with a recorded
          reason, never pass them through.

Depends on: solarfit.domain.assessment.{VisionRefinement, Obstacle}
(frozen, Day 0), solarfit.config.get_settings() for OPENAI_API_KEY
(frozen, Day 0).

Add the `openai` SDK to apps/api/pyproject.toml when you start this
(uv add openai) — deliberately not pre-installed by the Day-0 foundation.
"""

from solarfit.domain.assessment import Obstacle, VisionRefinement

RETAIN_IMAGERY = False  # VIS-06 — do not flip without a completed licence review.


def crop_to_boundary(imagery: bytes, boundary: dict) -> bytes:
    """VIS-01. Raises NotImplementedError until Person 3 implements it."""
    raise NotImplementedError


def refine_with_vision_model(cropped_imagery: bytes, boundary: dict) -> VisionRefinement:
    """VIS-02..04 + OBS-01..03. Single vision-LLM call returning both the
    corrected-boundary suggestion and the structured obstacle list (see
    VisionRefinement.obstacles). Raises NotImplementedError until Person
    3 implements it."""
    raise NotImplementedError


def validate_obstacle_polygon(obstacle: Obstacle, boundary: dict) -> bool:
    """OBS-03. True if the bounding polygon passes GEO-07/08's rules.
    Raises NotImplementedError until Person 3 implements it."""
    raise NotImplementedError
