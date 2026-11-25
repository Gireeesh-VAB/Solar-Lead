"""Every tunable in one place, read from environment variables (and an optional `.env` file next to this folder).

Defaults are the values the models were validated with in the solar-fitness app (rooftop_v1.yaml `yolo_ensemble` block), except
`roof_overlap_min`, which is 0.3 (see below).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    """Minimal KEY=VALUE reader. Real environment variables always win; a missing file is fine."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    #: Folder holding the *.pt segmentation models. Every model in it runs and the outputs are merged.
    model_dir: Path
    #: Google Maps key with "Maps Static API" enabled. Without it the service cannot fetch the satellite view (the pictures the models
    #: were trained on) and /detect answers "no_imagery" unless the caller supplies a frame itself.
    maps_api_key: str
    #: Per-model confidence floor passed to YOLO.
    model_conf: float
    imgsz: int
    max_det: int
    #: Mask IoU at/above which two detections count as the same obstacle.
    match_iou: float
    #: Merged obstacles scoring below this are dropped.
    min_ensemble_score: float
    #: Highest Static Maps zoom to request. Sharper than 19 makes the models read roof texture as obstacles.
    max_zoom: int
    #: The roof's bounding box plus this fraction on each side is cropped and enlarged (up to 4x) so the roof fills the frame.
    crop_margin: float
    #: An outline with less than this share of its area on the roof is a neighbour/tree/ground, not this roof's obstacle.
    #: 0.3 (the app used 0.5): large obstacles straddling the roof edge sit at ~40% on the roof and were thrown away at 0.5.
    roof_overlap_min: float
    #: Plausibility limits applied to what is left (geodesic area; the fraction is of the roof's own area).
    min_obstacle_area_m2: float
    max_obstacle_area_fraction: float
    device: str

    @property
    def imagery_available(self) -> bool:
        return bool(self.maps_api_key)


def get_settings() -> Settings:
    """Read fresh on every call (cheap), so a changed variable or a new `.env` takes effect without special handling."""
    _load_env_file(ROOT / ".env")
    env = os.environ.get
    model_dir = Path(env("OBSTACLE_MODEL_DIR", "weights"))
    if not model_dir.is_absolute():
        model_dir = ROOT / model_dir
    return Settings(
        model_dir=model_dir,
        maps_api_key=(env("GOOGLE_MAPS_API_KEY") or env("GOOGLE_SOLAR_API_KEY") or "").strip(),
        model_conf=float(env("OBSTACLE_MODEL_CONF", "0.25")),
        imgsz=int(env("OBSTACLE_IMGSZ", "640")),
        max_det=int(env("OBSTACLE_MAX_DET", "50")),
        match_iou=float(env("OBSTACLE_MATCH_IOU", "0.4")),
        min_ensemble_score=float(env("OBSTACLE_MIN_SCORE", "0.25")),
        max_zoom=int(env("OBSTACLE_MAX_ZOOM", "19")),
        crop_margin=float(env("OBSTACLE_CROP_MARGIN", "0.3")),
        roof_overlap_min=float(env("OBSTACLE_ROOF_OVERLAP_MIN", "0.3")),
        min_obstacle_area_m2=float(env("OBSTACLE_MIN_AREA_M2", "0.25")),
        max_obstacle_area_fraction=float(env("OBSTACLE_MAX_AREA_FRACTION", "0.5")),
        device=env("OBSTACLE_DEVICE", "cpu"),
    )
