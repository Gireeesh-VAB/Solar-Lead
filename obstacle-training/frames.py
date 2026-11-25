"""Satellite frames for training.

The training picture of a roof is the SAME picture the service builds at detection time: obstacle-service's own satellite_frame code (Static Maps
tile, roof + 30 % margin, enlarged up to 4x), imported - so a change to the service's framing automatically carries into training. Each roof is
downloaded once and cached under data/frames (local only, git-ignored); the cache is refreshed if the roof outline changes.

The Maps key is never printed or stored here: it comes from the environment / obstacle-service/.env, else is read from the solar-fitness
backend .env for this process only.
"""
import hashlib
import json
import re
import sys
from dataclasses import dataclass

import cv2
import numpy as np
from affine import Affine

import config

if str(config.SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(config.SERVICE_DIR))

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


@dataclass(frozen=True)
class TrainingFrame:
    image: np.ndarray  # BGR, as cv2/ultralytics expect
    transform: Affine  # pixel corner (col, row) -> EPSG:3857
    epsg: int = 3857


def maps_key() -> str:
    from obstacle_service.settings import get_settings

    key = get_settings().maps_api_key
    if key:
        return key
    try:
        text = config.APP_ENV_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(r"^\s*GOOGLE_MAPS_API_KEY\s*=\s*(\S+)", text, re.MULTILINE)
    return match.group(1).strip("\"'") if match else ""


def boundary_hash(boundary: dict) -> str:
    return hashlib.sha1(json.dumps(boundary, sort_keys=True).encode()).hexdigest()[:16]


def _paths(site_id: str):
    if not _UUID.match(site_id):
        raise ValueError(f"not a site id: {site_id!r}")
    return config.FRAMES_DIR / f"{site_id}.png", config.FRAMES_DIR / f"{site_id}.json"


def cached_frame(site_id: str, boundary: dict) -> TrainingFrame | None:
    """The cached frame for this roof outline, or None (nothing is downloaded)."""
    png, meta = _paths(site_id)
    if not (png.is_file() and meta.is_file()):
        return None
    try:
        info = json.loads(meta.read_text(encoding="utf-8"))
        if info.get("boundary") != boundary_hash(boundary):
            return None  # the outline changed since the frame was taken
        image = cv2.imread(str(png), cv2.IMREAD_COLOR)
        if image is None:
            return None
        return TrainingFrame(image, Affine(*info["transform"]), int(info.get("epsg", 3857)))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def get_frame(site_id: str, boundary: dict, *, allow_download: bool = True) -> TrainingFrame | None:
    """The training frame for a roof: from the cache, else downloaded once and cached. None when it cannot be had."""
    frame = cached_frame(site_id, boundary)
    if frame is not None or not allow_download:
        return frame
    key = maps_key()
    if not key:
        return None
    from obstacle_service.satellite_frame import fetch_roof_frame
    from obstacle_service.settings import get_settings

    s = get_settings()
    fetched = fetch_roof_frame(boundary, key, max_zoom=s.max_zoom, crop_margin=s.crop_margin)
    if fetched is None:
        return None
    image = cv2.imdecode(np.frombuffer(fetched.png_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return None
    png, meta = _paths(site_id)
    config.FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(png), image)
    meta.write_text(
        json.dumps({"boundary": boundary_hash(boundary), "transform": list(fetched.transform)[:6], "epsg": fetched.epsg}), encoding="utf-8"
    )
    return TrainingFrame(image, fetched.transform, fetched.epsg)
