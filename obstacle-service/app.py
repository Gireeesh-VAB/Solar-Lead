"""HTTP face of the obstacle service.

  GET  /health   which models are loaded, whether satellite imagery is configured, the active tunables (never the key)
  POST /detect   {"boundary": <GeoJSON Polygon, lng/lat>}  ->  {"status", "obstacles": [{polygon, confidence, votes, area_m2}], "stats"}
  POST /reload   load the weights folder again (obstacle-training calls this after installing a retrained model)

`stats` shows where detections are lost (raw per model -> after merge -> off-roof -> implausible -> returned), so a roof that "finds nothing"
can be diagnosed from one response.
Run:  python -m uvicorn app:app --port 8200
"""
from __future__ import annotations

import logging
from dataclasses import asdict, replace

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import shape

from obstacle_service import __version__
from obstacle_service.ensemble import get_ensemble, reset_ensembles
from obstacle_service.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("obstacle_service")

app = FastAPI(title="Obstacle service", version=__version__)


class DetectRequest(BaseModel):
    boundary: dict = Field(description="The roof outline: a GeoJSON Polygon in lng/lat (EPSG:4326).")
    roof_overlap_min: float | None = Field(default=None, ge=0, le=1, description="Override the on-roof share an outline needs (default from settings).")
    model_conf: float | None = Field(default=None, gt=0, le=1, description="Override the per-model confidence floor.")


@app.on_event("startup")
def _warm_up() -> None:
    ensemble = get_ensemble()
    if ensemble is None:
        log.warning("no models in %s - /detect will answer 503 until weights are copied in", get_settings().model_dir)
        return
    try:
        ensemble.warm_up()
    except Exception:  # noqa: BLE001 - the service still starts; /health reports it
        log.exception("model warm-up failed")


@app.get("/health")
def health() -> dict:
    s = get_settings()
    ensemble = get_ensemble(s)
    return {
        "ok": ensemble is not None,
        "version": __version__,
        "models": [p.name for p in ensemble.paths] if ensemble else [],
        "imagery": "configured" if s.imagery_available else "missing GOOGLE_MAPS_API_KEY",
        "settings": {
            "model_conf": s.model_conf, "imgsz": s.imgsz, "match_iou": s.match_iou, "min_ensemble_score": s.min_ensemble_score,
            "max_zoom": s.max_zoom, "crop_margin": s.crop_margin, "roof_overlap_min": s.roof_overlap_min,
            "min_obstacle_area_m2": s.min_obstacle_area_m2, "max_obstacle_area_fraction": s.max_obstacle_area_fraction,
        },
    }


@app.post("/reload")
def reload_models() -> dict:
    """Load the weights folder again - called by obstacle-training right after it installs a new model, so a retrained model is used at once
    without restarting the service. Requests already running finish on the models they started with."""
    s = get_settings()
    reset_ensembles()
    ensemble = get_ensemble(s)
    if ensemble is None:
        raise HTTPException(503, f"no models found in {s.model_dir}")
    ensemble.warm_up()
    log.info("models reloaded: %s", [p.name for p in ensemble.paths])
    return {"ok": True, "models": [p.name for p in ensemble.paths]}


@app.post("/detect")
def detect(req: DetectRequest) -> dict:
    try:
        geom = shape(req.boundary)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"boundary is not valid GeoJSON: {type(exc).__name__}") from exc
    if geom.geom_type != "Polygon" or geom.is_empty:
        raise HTTPException(422, "boundary must be a non-empty GeoJSON Polygon")

    s = get_settings()
    overrides = {k: v for k, v in (("roof_overlap_min", req.roof_overlap_min), ("model_conf", req.model_conf)) if v is not None}
    if overrides:
        s = replace(s, **overrides)

    ensemble = get_ensemble(s)
    if ensemble is None:
        raise HTTPException(503, f"no models found in {s.model_dir}")
    result = ensemble.detect(req.boundary, settings=s)
    if result.status == "no_imagery":
        raise HTTPException(
            502, "could not get the satellite view: set GOOGLE_MAPS_API_KEY with 'Maps Static API' enabled (see the service log for the HTTP status)"
        )
    if result.status == "bad_image":
        raise HTTPException(502, "the satellite picture could not be decoded")
    return {"status": result.status, "obstacles": [asdict(o) for o in result.obstacles], "stats": result.stats}
