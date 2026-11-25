"""Obstacle detection done by the stand-alone obstacle-service (the `obstacle-service` folder next to solar-fitness) instead of in this process.

Plugs into providers/obstacle_detectors.py's ObstacleDetector protocol exactly like the in-process YoloEnsembleDetector, so everything after
the detector - OBS-03 validation, the pending-candidate review flow, de-duplication against the site's history - is unchanged.

What moves to the service: fetching the Google satellite view, the three models, merging their answers, the on-roof filter and the clip to
the roof. What stays here: the roof boundary (sent as GeoJSON), the tunables in the config pack (`yolo_ensemble.roof_overlap_min` and
`model_conf` are forwarded with every call, so the pack stays the control surface), and everything downstream of the returned obstacles.

Never raises: an unreachable or failing service is logged and reported as "no obstacles found" - the same contract as every other
detector, so a scan degrades to an empty result and never breaks a roof check.
"""

from __future__ import annotations

import logging

import httpx

from solarfit.domain.assessment import Obstacle
from solarfit.packs.config_pack import get_yolo_ensemble_params
from solarfit.providers.vision import CroppedImagery

logger = logging.getLogger(__name__)

__all__ = ["RemoteObstacleDetector"]


class RemoteObstacleDetector:
    """ObstacleDetector backed by an obstacle-service over HTTP."""

    name = "obstacle_service"
    #: The service brings its own satellite view, so callers can skip the Solar API download (see solar_imagery_needed()).
    needs_solar_imagery = False

    def __init__(self, base_url: str, timeout_s: float = 90.0):
        self._url = base_url.strip().rstrip("/")
        self._timeout = timeout_s

    def _request_body(self, boundary: dict) -> dict:
        body: dict = {"boundary": boundary}
        params = get_yolo_ensemble_params()
        for key in ("roof_overlap_min", "model_conf"):
            if params.get(key) is not None:
                body[key] = float(params[key])
        return body

    def detect(self, cropped: CroppedImagery | None, boundary: dict) -> list[Obstacle]:
        if not boundary:
            return []
        try:
            response = httpx.post(f"{self._url}/detect", json=self._request_body(boundary), timeout=self._timeout)
        except httpx.HTTPError as exc:
            # The exception TEXT can contain the URL; the type is enough to act on.
            logger.warning("obstacle-service at %s unreachable (%s) - reporting no obstacles", self._url, type(exc).__name__)
            return []
        if response.status_code != 200:
            logger.warning("obstacle-service answered %s: %s", response.status_code, response.text[:300])
            return []
        try:
            payload = response.json()
            found = payload["obstacles"]
        except (ValueError, KeyError, TypeError):
            logger.warning("obstacle-service sent an unreadable answer - reporting no obstacles")
            return []

        obstacles: list[Obstacle] = []
        for item in found:
            try:
                obstacles.append(
                    Obstacle(
                        type="other",  # the models are single-class: the type is not guessed
                        bounding_polygon=item["polygon"],
                        confidence=round(float(item["confidence"]), 4),
                        source="cv_detector",
                    )
                )
            except (KeyError, TypeError, ValueError):
                logger.warning("obstacle-service sent a malformed obstacle - skipped")
        logger.info("obstacle-service: %d obstacles (stats %s)", len(obstacles), payload.get("stats"))
        return obstacles
