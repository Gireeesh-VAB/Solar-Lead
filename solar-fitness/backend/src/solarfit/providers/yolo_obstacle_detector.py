"""Phase 7 — the YOLO obstacle-detection ensemble.

Every `*.pt` segmentation model found in settings.yolo_model_dir runs on
the same roof image - a Google satellite frame by default, the picture the
models were trained on (providers/satellite_frame.py) - and their outputs
are blended into one list of obstacles ("a + b + c"):

  1. each model predicts instance masks with its own confidence;
  2. detections from ANY models whose masks overlap (IoU >= match_iou, or
     one lies mostly inside the other) are one physical obstacle; the most
     confident model's outline is kept and the duplicates dropped;
  3. the obstacle's confidence is the HIGHEST confidence any model gave it
     (the number a single YOLO tool would show), and how many models saw it
     is kept as `votes`;
  4. an outline with under half its area on the roof (a neighbouring
     building, a tree) is discarded; one straddling the edge is clipped.

This is the same recipe as the VAB obstacle-service these models ship with.

The ensemble is a union ("a + b + c"): an obstacle ONE model saw is still
surfaced. An earlier version divided the summed confidences by the model
count, which silently dropped every lone detection under 0.6 - on real
roofs that discarded 1-2 of every 3-4 obstacles the models had found.
That strictness is unnecessary now that nothing a model finds is applied
without the customer's Confirm / Edit / Ignore (engine/obstacles.py holds
every cv_detector obstacle for review); a wrong one costs one click.

The models are single-class ("obstacle"), so every fused detection is
typed "other" — the type is not guessed.

Plugs into providers/obstacle_detectors.py's ObstacleDetector protocol and
therefore inherits OBS-03 validation, the auto-apply split and the SITE-05
versioned exclusions unchanged. Never raises: a model that fails to load
or run is skipped and the others still vote.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image
from pyproj import Transformer
from shapely.geometry import Polygon, shape

from solarfit.config import get_settings
from solarfit.domain.assessment import Obstacle
from solarfit.packs.config_pack import get_yolo_ensemble_params
from solarfit.providers.obstacle_detectors import clip_polygon_to_boundary as _clip_to_boundary
from solarfit.providers.satellite_frame import fetch_roof_frame
from solarfit.providers.vision import CroppedImagery, crop_to_boundary, fetch_rgb_imagery

logger = logging.getLogger(__name__)

__all__ = ["Detection", "FusedDetection", "YoloEnsembleDetector", "fuse_detections"]


@dataclass(frozen=True)
class Detection:
    """One model's raw detection, as a polygon in the crop's PIXEL space."""

    model_index: int
    polygon: Polygon
    confidence: float


@dataclass(frozen=True)
class FusedDetection:
    polygon: Polygon  # pixel space
    score: float  # highest confidence any model gave it, 0..1
    votes: int  # how many distinct models saw it


#: An outline with at least this share of its area inside another is the same
#: object (a model's own box-NMS lets nested outlines of one object through).
_CONTAINED = 0.6


def _iou(a: Polygon, b: Polygon) -> float:
    """How strongly two outlines are the same object: their IoU, or - when
    one lies mostly inside the other - the containment share (>= 0.6)."""
    if a.is_empty or b.is_empty:
        return 0.0
    inter = a.intersection(b).area
    if inter <= 0.0:
        return 0.0
    iou = inter / (a.area + b.area - inter)
    contained = inter / min(a.area, b.area)
    return max(iou, contained if contained >= _CONTAINED else 0.0)


def fuse_detections(
    detections: list[Detection], *, n_models: int, match_iou: float, min_score: float
) -> list[FusedDetection]:
    """Pure fusion step (no YOLO, no imagery) — see the module docstring.

    Greedy by descending confidence: each detection joins the existing
    cluster it overlaps most (IoU >= match_iou, or mostly inside it, against
    the cluster's outline), else seeds a new one. A model contributes at
    most one vote per cluster — its highest-confidence member — and the
    cluster's outline is that of its most confident detection."""
    if n_models <= 0:
        return []

    clusters: list[dict] = []
    for det in sorted(detections, key=lambda d: d.confidence, reverse=True):
        if det.polygon.is_empty or not det.polygon.is_valid:
            det = Detection(det.model_index, det.polygon.buffer(0), det.confidence)
            if det.polygon.is_empty:
                continue

        best, best_iou = None, match_iou
        for cluster in clusters:
            iou = _iou(det.polygon, cluster["outline"])
            if iou >= best_iou:
                best, best_iou = cluster, iou

        if best is None:
            clusters.append(
                {"outline": det.polygon, "votes": {det.model_index: det.confidence}}
            )
            continue

        # The cluster keeps its seed's outline - the most confident one,
        # since detections are visited best-first - and the duplicates are
        # dropped. Not the union: merging two models' slightly different
        # outlines bloats the shape, and a bloated outline can slip below
        # the on-roof overlap test and lose a real obstacle.
        best["votes"][det.model_index] = max(
            best["votes"].get(det.model_index, 0.0), det.confidence
        )

    fused: list[FusedDetection] = []
    for cluster in clusters:
        score = max(cluster["votes"].values())
        if score < min_score:
            continue
        outline = cluster["outline"]
        if outline.geom_type != "Polygon":  # a mask that came out as several pieces
            outline = outline.convex_hull
        fused.append(FusedDetection(polygon=outline, score=min(score, 1.0), votes=len(cluster["votes"])))
    # Most confident first; among equals, the one more models agree on.
    return sorted(fused, key=lambda f: (f.score, f.votes), reverse=True)


def _solar_crop_for(boundary: dict) -> CroppedImagery | None:
    """The Solar API aerial crop of `boundary` - the fallback input when the
    satellite frame cannot be had. None if that fails too."""
    if not boundary:
        return None
    try:
        centre = shape(boundary).centroid
        return crop_to_boundary(fetch_rgb_imagery(centre.y, centre.x), boundary)
    except Exception as exc:  # noqa: BLE001 - no imagery is an ordinary outcome
        logger.info("YOLO ensemble: no Solar API imagery either - %s", exc)
        return None


def _mostly_on_roof(geojson: dict, roof, minimum: float) -> bool:
    """True when at least `minimum` of the outline's area lies on the roof.
    Geometry trouble counts as "keep" - the later clip and OBS-03 decide."""
    try:
        outline = shape(geojson).buffer(0)
        if outline.is_empty or outline.area <= 0:
            return False
        return outline.intersection(roof).area / outline.area >= minimum
    except Exception:  # noqa: BLE001
        return True


def _pixel_polygon_to_geojson(poly: Polygon, cropped: CroppedImagery) -> dict | None:
    """Pixel-space outline -> GeoJSON Polygon in EPSG:4326, through the
    crop's own affine transform (same discipline as providers/vision.py's
    bbox conversion)."""
    poly = poly.simplify(1.0, preserve_topology=True)
    if poly.is_empty or poly.geom_type != "Polygon":
        return None
    native = [cropped.transform * (col, row) for col, row in poly.exterior.coords]
    if cropped.crs is not None and cropped.crs.to_epsg() != 4326:
        to_wgs84 = Transformer.from_crs(cropped.crs, "EPSG:4326", always_xy=True)
        native = [to_wgs84.transform(x, y) for x, y in native]
    ring = [list(pt) for pt in native]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


class YoloEnsembleDetector:
    """ObstacleDetector (providers/obstacle_detectors.py) blending every
    YOLO model in a folder."""

    name = "yolo_ensemble"

    def __init__(self, model_paths: list[Path]):
        self._paths = sorted(model_paths)
        self._models: list | None = None
        # Loading and predicting on a shared ultralytics model is not
        # thread-safe, and the worker may run several tasks at once.
        self._lock = threading.Lock()

    @property
    def n_models(self) -> int:
        return len(self._paths)

    def _load(self) -> list:
        if self._models is None:
            from ultralytics import YOLO  # heavy import — only when actually used

            loaded = []
            for path in self._paths:
                try:
                    loaded.append(YOLO(str(path)))
                    logger.info("YOLO obstacle model loaded: %s", path.name)
                except Exception:
                    logger.exception("Could not load YOLO model %s — skipping it", path)
                    loaded.append(None)
            self._models = loaded
        return self._models

    def warm_up(self) -> None:
        """Load the weights now (and import PyTorch) instead of on the first
        assessment — the cold start can run to tens of seconds, which would
        blow the async-task timeout for whichever check came first."""
        with self._lock:
            self._load()

    def _predict_one(self, model, image: Image.Image, params: dict) -> list[tuple[Polygon, float]]:
        result = model.predict(
            image,
            conf=float(params["model_conf"]),
            imgsz=int(params["imgsz"]),
            max_det=int(params["max_det"]),
            device="cpu",
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

    @staticmethod
    def _satellite_api_key(params: dict) -> str:
        """The Maps key to fetch the satellite frame with, or "" when that
        input is switched off in the config pack or no key is configured."""
        if str(params.get("imagery", "static_satellite")) != "static_satellite":
            return ""
        settings = get_settings()
        return settings.google_maps_api_key or settings.google_solar_api_key

    @property
    def needs_solar_imagery(self) -> bool:
        """True when callers must still supply the Solar API crop - i.e. when
        this detector cannot get its own satellite frame (see
        providers/satellite_frame.py). Lets a caller skip that download."""
        return not self._satellite_api_key(get_yolo_ensemble_params())

    def detect(self, cropped: CroppedImagery | None, boundary: dict) -> list[Obstacle]:
        if not self._paths:
            return []
        params = get_yolo_ensemble_params()

        # The models were trained on Google satellite screenshots - show them
        # that (satellite_frame.py), and fall back to the supplied Solar API
        # crop only if it cannot be had.
        frame = None
        api_key = self._satellite_api_key(params)
        if api_key and boundary:
            frame = fetch_roof_frame(
                boundary,
                api_key,
                max_zoom=int(params.get("max_zoom", 19)),
                crop_margin=float(params.get("crop_margin", 0.3)),
            )
        cropped = frame or cropped
        if cropped is None:
            # The caller skipped the Solar download because we said we would
            # bring our own frame - and that failed (Static Maps API not
            # enabled for the key, network...). Fall back to the Solar API
            # crop rather than silently reporting "nothing found".
            cropped = _solar_crop_for(boundary)
        if cropped is None:
            logger.warning("YOLO ensemble: no imagery to run on (neither satellite frame nor Solar API crop)")
            return []
        try:
            image = Image.open(BytesIO(cropped.png_bytes)).convert("RGB")
        except Exception:
            logger.exception("YOLO ensemble: could not decode the roof crop")
            return []

        detections: list[Detection] = []
        with self._lock:
            for index, model in enumerate(self._load()):
                if model is None:
                    continue
                try:
                    for polygon, conf in self._predict_one(model, image, params):
                        detections.append(Detection(index, polygon, conf))
                except Exception:
                    logger.exception("YOLO model %s failed on this crop — skipping it", self._paths[index].name)

        fused = fuse_detections(
            detections,
            n_models=self.n_models,
            match_iou=float(params["match_iou"]),
            min_score=float(params["min_ensemble_score"]),
        )

        try:
            boundary_geom = shape(boundary) if boundary else None
            if boundary_geom is not None and not boundary_geom.is_valid:
                boundary_geom = boundary_geom.buffer(0)
        except Exception:  # noqa: BLE001 - a bad boundary just skips the clip
            boundary_geom = None

        # An outline that is mostly OFF the roof is a neighbouring building, a
        # tree or the ground - not this roof's obstacle (the reference
        # service's roof_overlap_min). One that straddles the edge is kept
        # and clipped to the roof below.
        overlap_min = float(params.get("roof_overlap_min", 0.5))

        obstacles: list[Obstacle] = []
        for item in fused:
            geojson = _pixel_polygon_to_geojson(item.polygon, cropped)
            if geojson is None:
                continue
            if boundary_geom is not None and overlap_min > 0 and not _mostly_on_roof(geojson, boundary_geom, overlap_min):
                continue
            geojson = _clip_to_boundary(geojson, boundary_geom)
            if geojson is None:
                continue
            obstacles.append(
                Obstacle(
                    type="other",
                    bounding_polygon=geojson,
                    confidence=round(float(item.score), 4),
                    source="cv_detector",
                )
            )
        logger.info(
            "YOLO ensemble: %d raw detections from %d models -> %d obstacles",
            len(detections),
            self.n_models,
            len(obstacles),
        )
        return obstacles
