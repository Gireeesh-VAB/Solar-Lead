"""The YOLO obstacle-detection ensemble.

Every `*.pt` segmentation model in the model folder runs on the same roof picture and their outputs are blended into one list:

  1. each model predicts instance masks with its own confidence;
  2. detections from ANY models whose masks overlap (IoU >= match_iou, or one lies mostly inside the other) are one physical obstacle;
     the most confident model's outline is kept and the duplicates dropped;
  3. the obstacle's confidence is the HIGHEST confidence any model gave it, and how many models saw it is kept as `votes`;
  4. an outline with under `roof_overlap_min` of its area on the roof (a neighbouring building, a tree) is discarded; one straddling the
     edge is clipped to the roof;
  5. what is left must be a plausible obstacle (valid geometry, inside the roof, sensible size).

The ensemble is a UNION: an obstacle one model saw is still reported. (Averaging confidences over the model count silently dropped every
lone detection under 0.6 - on real roofs that discarded 1-2 of every 3-4 obstacles.) The models are single-class, so nothing is typed.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from PIL import Image
from shapely.geometry import Polygon, shape

from obstacle_service.geometry import (
    clip_polygon_to_boundary,
    geodesic_area_m2,
    is_plausible_obstacle,
    mostly_on_roof,
    pixel_polygon_to_geojson,
)
from obstacle_service.satellite_frame import Frame, fetch_roof_frame
from obstacle_service.settings import Settings, get_settings

logger = logging.getLogger(__name__)

#: An outline with at least this share of its area inside another is the same object (a model's own box-NMS lets nested outlines through).
_CONTAINED = 0.6


@dataclass(frozen=True)
class Detection:
    """One model's raw detection, as a polygon in the frame's PIXEL space."""

    model_index: int
    polygon: Polygon
    confidence: float


@dataclass(frozen=True)
class FusedDetection:
    polygon: Polygon  # pixel space
    score: float  # highest confidence any model gave it, 0..1
    votes: int  # how many distinct models saw it


@dataclass(frozen=True)
class Obstacle:
    polygon: dict  # GeoJSON Polygon, lng/lat
    confidence: float
    votes: int
    area_m2: float


@dataclass
class DetectionResult:
    #: "ok" | "no_models" | "no_imagery" | "bad_image"
    status: str
    obstacles: list[Obstacle] = field(default_factory=list)
    #: Where detections are lost along the way - the first thing to read when a roof "finds nothing".
    stats: dict = field(default_factory=dict)


def _overlap(a: Polygon, b: Polygon) -> float:
    """How strongly two outlines are the same object: their IoU, or - when one lies mostly inside the other - the containment share."""
    if a.is_empty or b.is_empty:
        return 0.0
    inter = a.intersection(b).area
    if inter <= 0.0:
        return 0.0
    iou = inter / (a.area + b.area - inter)
    contained = inter / min(a.area, b.area)
    return max(iou, contained if contained >= _CONTAINED else 0.0)


def fuse_detections(detections: list[Detection], *, n_models: int, match_iou: float, min_score: float) -> list[FusedDetection]:
    """Pure fusion step (no YOLO, no imagery). Greedy by descending confidence: each detection joins the existing cluster it overlaps most,
    else seeds a new one. A model contributes at most one vote per cluster; the cluster's outline is its most confident detection's."""
    if n_models <= 0:
        return []

    clusters: list[dict] = []
    for det in sorted(detections, key=lambda d: d.confidence, reverse=True):
        if det.polygon.is_empty or not det.polygon.is_valid:
            det = Detection(det.model_index, det.polygon.buffer(0), det.confidence)
            if det.polygon.is_empty:
                continue

        best, best_overlap = None, match_iou
        for cluster in clusters:
            value = _overlap(det.polygon, cluster["outline"])
            if value >= best_overlap:
                best, best_overlap = cluster, value

        if best is None:
            clusters.append({"outline": det.polygon, "votes": {det.model_index: det.confidence}})
            continue
        # The cluster keeps its seed's outline (the most confident, since detections are visited best-first), NOT a union: merging two models'
        # slightly different outlines bloats the shape and can push a real obstacle under the on-roof test.
        best["votes"][det.model_index] = max(best["votes"].get(det.model_index, 0.0), det.confidence)

    fused: list[FusedDetection] = []
    for cluster in clusters:
        score = max(cluster["votes"].values())
        if score < min_score:
            continue
        outline = cluster["outline"]
        if outline.geom_type != "Polygon":  # a mask that came out as several pieces
            outline = outline.convex_hull
        fused.append(FusedDetection(polygon=outline, score=min(score, 1.0), votes=len(cluster["votes"])))
    return sorted(fused, key=lambda f: (f.score, f.votes), reverse=True)


class Ensemble:
    """Every YOLO model in a folder, loaded once and shared."""

    def __init__(self, model_paths: list[Path]):
        self.paths = sorted(model_paths)
        self._models: list | None = None
        # Loading and predicting on a shared ultralytics model is not thread-safe.
        self._lock = threading.Lock()

    @property
    def n_models(self) -> int:
        return len(self.paths)

    def _load(self) -> list:
        if self._models is None:
            from ultralytics import YOLO  # heavy import - only when actually used

            loaded = []
            for path in self.paths:
                try:
                    loaded.append(YOLO(str(path)))
                    logger.info("obstacle model loaded: %s", path.name)
                except Exception:
                    logger.exception("could not load model %s - skipping it", path)
                    loaded.append(None)
            self._models = loaded
        return self._models

    def warm_up(self) -> None:
        """Load the weights now (and import PyTorch) instead of on the first request - the cold start can take tens of seconds."""
        with self._lock:
            self._load()

    @staticmethod
    def _predict_one(model, image: Image.Image, s: Settings) -> list[tuple[Polygon, float]]:
        result = model.predict(
            image, conf=s.model_conf, imgsz=s.imgsz, max_det=s.max_det, device=s.device,
            retina_masks=True,  # masks at the input's own resolution, as the models were validated
            verbose=False,
        )[0]
        confs = [float(c) for c in result.boxes.conf.tolist()] if result.boxes is not None else []
        out: list[tuple[Polygon, float]] = []
        if result.masks is not None:
            for xy, conf in zip(result.masks.xy, confs, strict=False):
                if len(xy) >= 3:
                    out.append((Polygon(xy), conf))
        elif result.boxes is not None:  # a detect-only model: fall back to its boxes
            for (x1, y1, x2, y2), conf in zip(result.boxes.xyxy.tolist(), confs, strict=False):
                out.append((Polygon([(x1, y1), (x2, y1), (x2, y2), (x1, y2)]), conf))
        return out

    def detect(self, boundary: dict, *, frame: Frame | None = None, settings: Settings | None = None) -> DetectionResult:
        """Obstacles on the roof `boundary` (GeoJSON Polygon, lng/lat). `frame` lets a caller supply the picture; otherwise the satellite view is
        fetched with the configured Maps key. Never raises for an ordinary outcome: see DetectionResult.status."""
        s = settings or get_settings()
        stats: dict = {"models": self.n_models}
        if not self.paths:
            return DetectionResult("no_models", stats=stats)

        if frame is None and s.imagery_available and boundary:
            frame = fetch_roof_frame(boundary, s.maps_api_key, max_zoom=s.max_zoom, crop_margin=s.crop_margin)
            stats["frame_source"] = "static_maps"
        elif frame is not None:
            stats["frame_source"] = "supplied"
        if frame is None:
            return DetectionResult("no_imagery", stats=stats)
        try:
            image = Image.open(BytesIO(frame.png_bytes)).convert("RGB")
        except Exception:
            logger.exception("could not decode the roof picture")
            return DetectionResult("bad_image", stats=stats)
        stats["frame_px"] = [image.width, image.height]

        detections: list[Detection] = []
        per_model: dict[str, int] = {}
        with self._lock:
            for index, model in enumerate(self._load()):
                name = self.paths[index].name
                if model is None:
                    per_model[name] = -1  # failed to load
                    continue
                try:
                    found = self._predict_one(model, image, s)
                except Exception:
                    logger.exception("model %s failed on this picture - skipping it", name)
                    per_model[name] = -2  # failed to run
                    continue
                per_model[name] = len(found)
                detections += [Detection(index, polygon, conf) for polygon, conf in found]
        stats["raw_per_model"] = per_model

        fused = fuse_detections(detections, n_models=self.n_models, match_iou=s.match_iou, min_score=s.min_ensemble_score)
        stats["after_merge"] = len(fused)

        roof = None
        if boundary:
            try:
                roof = shape(boundary)
                if not roof.is_valid:
                    roof = roof.buffer(0)
            except Exception:  # noqa: BLE001 - a bad boundary just skips the roof filter and clip
                roof = None

        obstacles: list[Obstacle] = []
        dropped_off_roof = dropped_implausible = 0
        for item in fused:
            geojson = pixel_polygon_to_geojson(item.polygon, frame)
            if geojson is None:
                continue
            if roof is not None and s.roof_overlap_min > 0 and not mostly_on_roof(geojson, roof, s.roof_overlap_min):
                dropped_off_roof += 1
                continue
            geojson = clip_polygon_to_boundary(geojson, roof)
            if geojson is None:
                dropped_off_roof += 1
                continue
            if boundary and not is_plausible_obstacle(
                geojson, boundary, min_area_m2=s.min_obstacle_area_m2, max_fraction=s.max_obstacle_area_fraction
            ):
                dropped_implausible += 1
                continue
            obstacles.append(Obstacle(polygon=geojson, confidence=round(float(item.score), 4), votes=item.votes, area_m2=round(geodesic_area_m2(shape(geojson)), 2)))
        stats["dropped_off_roof"] = dropped_off_roof
        stats["dropped_implausible"] = dropped_implausible
        stats["returned"] = len(obstacles)
        logger.info("obstacle detect: %s", stats)
        return DetectionResult("ok", obstacles, stats)


# --- one shared ensemble per model folder -------------------------------------------------------------------------------------------------

_ENSEMBLES: dict[str, Ensemble] = {}


def reset_ensembles() -> None:
    """Forget the loaded models, so the next get_ensemble() reads the weights folder again (used after a new model is installed)."""
    _ENSEMBLES.clear()


def get_ensemble(settings: Settings | None = None) -> Ensemble | None:
    """The shared ensemble for the configured model folder, or None when it holds no *.pt files. Only a SUCCESSFUL lookup is remembered:
    "no models found" is checked again on the next call, so copying the weights in is enough (no restart)."""
    s = settings or get_settings()
    key = str(s.model_dir)
    cached = _ENSEMBLES.get(key)
    if cached is not None:
        return cached
    paths = sorted(s.model_dir.glob("*.pt")) if s.model_dir.is_dir() else []
    if not paths:
        logger.warning("model folder %s has no *.pt models", s.model_dir)
        return None
    logger.info("obstacle ensemble: %d models from %s", len(paths), s.model_dir)
    _ENSEMBLES[key] = Ensemble(paths)
    return _ENSEMBLES[key]
