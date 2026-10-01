"""Owner: Person 3 (Vision, Panorama & ML).

Phase 7 — a pluggable obstacle-detector architecture.

providers/vision.py::refine_with_vision_model() already implements a
real, validated Obstacle producer (OBS-01/02/03): the GPT-4 Vision call,
tagged `source="vision_llm"` on every Obstacle it returns. Everything
downstream of a `list[Obstacle]` — OBS-03's validate_obstacle_polygon(),
engine/obstacles.py's apply_or_flag()/reject_applied_obstacle(), both
Celery tasks, and repositories/sites.py's persistence layer — was
already fully generic over where that list came from before this module
existed (confirmed by inspection, not assumed). This module gives that
genericness an actual seam: a `ObstacleDetector` Protocol a SECOND,
independent detector (the roadmap's stated goal — a CV segmentation
model for water tanks/HVAC/vents) can implement later without touching
any of the above.

No second detector is wired in yet — `get_configured_detectors()`
returns `[]` today. This is the seam, not a second model. Adding one
later means implementing `ObstacleDetector` and returning it from that
function; nothing else in the pipeline changes.

Deliberately NOT a home for the vision-LLM detector itself: OBS-01's own
constraint ("never a second crop, never a second call") means its
obstacle extraction has to stay piggybacked on VIS-02's single
completion inside refine_with_vision_model() — it can't be refactored
into an independently-callable `detect(cropped, boundary)` without
literally making a second call, which is the exact thing OBS-01
forbids. This Protocol is for detectors that GENUINELY run standalone.
"""

import logging
from typing import Protocol

from solarfit.domain.assessment import Obstacle
from solarfit.providers.vision import CroppedImagery

logger = logging.getLogger(__name__)


class ObstacleDetector(Protocol):
    """One independent source of obstacle detections for a cropped roof
    image. `name` tags which detector a caller is looking at (distinct
    from `Obstacle.source`, which tags each individual detection —
    a detector could in principle return obstacles from more than one
    source if it wraps another detector, though none does today).

    Implementations must never raise (see detect_obstacles() below,
    which also isolates one detector's failure from the others) — same
    "absence is data, not an exception" discipline as every other
    provider in this codebase. A detector with nothing to report, or
    that failed internally, returns an empty list, not None and not an
    exception.
    """

    name: str

    def detect(self, cropped: CroppedImagery, boundary: dict) -> list[Obstacle]: ...


def get_configured_detectors() -> list[ObstacleDetector]:
    """The pluggable seam itself. Empty today — no second detector
    exists yet. A future CV detector gets wired in by returning an
    instance of it here; every caller of detect_obstacles() picks it up
    with no further changes."""
    return []


def detect_obstacles(
    cropped: CroppedImagery, boundary: dict, *, detectors: list[ObstacleDetector]
) -> list[Obstacle]:
    """Runs every configured detector, isolated from each other's
    failures, and returns the combined list. Order is detector-
    declaration order.

    Deliberately does NOT deduplicate or rank across detectors — two
    detectors flagging the same real water tank as two separate
    Obstacle entries is future work (a cross-detector matching policy
    would need real detections from more than one detector to design
    against), not silently guessed at here. OBS-03's
    validate_obstacle_polygon() and engine/obstacles.py's threshold
    split still apply uniformly to the combined list downstream, same
    as they already do for the vision-LLM's own obstacles today.
    """
    results: list[Obstacle] = []
    for detector in detectors:
        try:
            results.extend(detector.detect(cropped, boundary))
        except Exception:
            logger.exception(
                "Obstacle detector %s failed — continuing without it", detector.name
            )
    return results
