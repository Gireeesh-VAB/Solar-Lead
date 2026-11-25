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

The first such detector is providers/yolo_obstacle_detector.py — an
ensemble of every YOLO model in settings.yolo_model_dir, registered by
`get_configured_detectors()` below. Adding another means implementing
`ObstacleDetector` and returning it from that function; nothing else in
the pipeline changes.

Deliberately NOT a home for the vision-LLM detector itself: OBS-01's own
constraint ("never a second crop, never a second call") means its
obstacle extraction has to stay piggybacked on VIS-02's single
completion inside refine_with_vision_model() — it can't be refactored
into an independently-callable `detect(cropped, boundary)` without
literally making a second call, which is the exact thing OBS-01
forbids. This Protocol is for detectors that GENUINELY run standalone.
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from solarfit.config import _BACKEND_DIR, get_settings
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

    # Optional: a detector that fetches its own imagery (the YOLO ensemble
    # gets a satellite frame) reports False here when the shared Solar API
    # crop is not needed, so a caller can skip that download and pass
    # `cropped=None`. Absent means "needs it".
    #   needs_solar_imagery: bool

    def detect(self, cropped: CroppedImagery | None, boundary: dict) -> list[Obstacle]: ...


def solar_imagery_needed(detectors: list[ObstacleDetector]) -> bool:
    """Whether any detector still needs the Solar API crop."""
    return any(getattr(d, "needs_solar_imagery", True) for d in detectors)


def clip_polygon_to_boundary(geojson: dict, boundary_geom) -> dict | None:
    """Clip an obstacle's GeoJSON polygon to a roof boundary geometry.

    An obstacle cannot sit outside the roof. Detector masks are
    pixel-based, so along the roof edge they can poke past it, and OBS-03
    (providers/vision.py::validate_obstacle_polygon) rejects any obstacle
    the boundary does not fully cover — which would throw away a real
    obstacle just because it straddles the edge. Clipping keeps the part
    that is on the roof. Returns None when nothing is left; returns the
    input unchanged when there is no usable boundary or on any geometry
    error (the caller's own validation still applies)."""
    from shapely.geometry import mapping, shape

    if boundary_geom is None or boundary_geom.is_empty:
        return geojson
    try:
        # Clip to the boundary inset by a hair (1e-7 deg ~ 1 cm): an exact
        # intersection puts the new vertices ON the boundary line, where
        # floating-point rounding leaves them a hair outside, and
        # validate_obstacle_polygon()'s strict covers() check then rejects
        # the very polygon we just clipped to fit.
        inner = boundary_geom.buffer(-1e-7)
        target = inner if not inner.is_empty else boundary_geom
        clipped = shape(geojson).buffer(0).intersection(target)
    except Exception:  # noqa: BLE001 - bad geometry must never break the pipeline
        return geojson
    if clipped.is_empty:
        return None
    if clipped.geom_type != "Polygon":
        polygons = [g for g in getattr(clipped, "geoms", []) if g.geom_type == "Polygon" and not g.is_empty]
        if not polygons:
            return None
        clipped = max(polygons, key=lambda g: g.area)
    return mapping(clipped)


@lru_cache(maxsize=4)
def _yolo_ensemble_for(model_dir: str) -> ObstacleDetector | None:
    """One cached ensemble per model folder, so the weights are loaded
    once per worker process rather than once per assessment."""
    from solarfit.providers.yolo_obstacle_detector import YoloEnsembleDetector

    folder = Path(model_dir)
    paths = sorted(folder.glob("*.pt")) if folder.is_dir() else []
    if not paths:
        logger.warning("yolo_model_dir %r has no *.pt models — YOLO ensemble disabled", model_dir)
        return None
    logger.info("YOLO obstacle ensemble: %d models from %s", len(paths), model_dir)
    return YoloEnsembleDetector(paths)


def get_configured_detectors() -> list[ObstacleDetector]:
    """The pluggable seam itself. Returns the YOLO ensemble when
    settings.yolo_model_dir points at a folder of `*.pt` models, else
    nothing. A further detector gets wired in by appending it here;
    every caller of detect_obstacles() picks it up with no other
    changes."""
    detectors: list[ObstacleDetector] = []
    model_dir = get_settings().yolo_model_dir.strip()
    if model_dir:
        # A relative path means "relative to the backend folder", not to
        # whatever directory the worker happened to be started from.
        path = Path(model_dir)
        if not path.is_absolute():
            path = _BACKEND_DIR / path
        ensemble = _yolo_ensemble_for(str(path))
        if ensemble is not None:
            detectors.append(ensemble)
    return detectors


def detect_obstacles(
    cropped: CroppedImagery | None, boundary: dict, *, detectors: list[ObstacleDetector]
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
