# obstacle-service

Finds obstacles (water tanks, stair/lift rooms, AC units, existing panels ...) on a rooftop. Stand-alone: it has **no dependency on the
solar-fitness app** and can be run, tested and deployed on its own. Give it a roof outline; it fetches a Google satellite view of that roof,
runs three YOLO segmentation models on it, merges their answers and returns the obstacles as GeoJSON polygons.

```
roof outline (GeoJSON, lng/lat)
   -> Google Static Maps satellite view, centred on the roof, zoom <= 19
   -> cropped to the roof + 30 % margin and enlarged (up to 4x), as the models were trained
   -> 3 models predict masks (640 px, full-resolution masks)
   -> merge: overlapping outlines are one obstacle, the most confident outline wins, confidence = highest, votes = how many models saw it
   -> drop outlines that are mostly off the roof (neighbours, trees); clip the ones straddling the edge
   -> drop implausible shapes (not inside the roof, < 0.25 m2, > 50 % of the roof)
   -> obstacles
```

## Folder

| Path | What |
|---|---|
| `app.py` | HTTP API: `GET /health`, `POST /detect`, `POST /reload` |
| `obstacle_service/ensemble.py` | the models, merging, the `detect()` flow, the shared model registry |
| `obstacle_service/satellite_frame.py` | the Google satellite view + how its pixels map back to lng/lat |
| `obstacle_service/geometry.py` | pixels -> lng/lat, on-roof test, clipping, plausibility checks |
| `obstacle_service/settings.py` | every tunable (environment variables / `.env`) |
| `weights/` | the models: `obstacle_pilot_v1.pt`, `obstacle_combined_v1.pt`, `obstacle_combined_v2.pt` |
| `tests/` | 36 tests, no network and no weights needed |
| `scripts/smoke_detect.py` | call a running service on a roof and see where detections were lost |
| `run.ps1` | start the service on port 8200 |

## Run

1. `copy .env.example .env` and set `GOOGLE_MAPS_API_KEY` (a key with **Maps Static API** enabled). `.env` is git-ignored.
2. Packages: `pip install -r requirements.txt` in a venv here. (`run.ps1` falls back to the solar-fitness backend's environment, which already has them all.)
3. `.\run.ps1`  ->  http://127.0.0.1:8200  (interactive docs at `/docs`)

```
GET  /health
POST /detect   {"boundary": {"type":"Polygon","coordinates":[[[lng,lat],...]]}, "roof_overlap_min": 0.3 (optional), "model_conf": 0.25 (optional)}
```

`POST /reload` loads the weights folder again (called by `obstacle-training` right after it installs a retrained model, so no restart is needed).

`/detect` answers `{"status": "ok", "obstacles": [{polygon, confidence, votes, area_m2}], "stats": {...}}`. **`stats` is the diagnostic**: raw
detections per model -> after merge -> dropped off-roof -> dropped implausible -> returned. When a roof "finds nothing", the stage where the
number falls to zero tells you why. Errors: `422` bad boundary, `503` no models found, `502` no satellite view (missing/!enabled key).

## Tunables (environment or `.env`)

| Variable | Default | Meaning |
|---|---|---|
| `GOOGLE_MAPS_API_KEY` | - | Maps Static API key (falls back to `GOOGLE_SOLAR_API_KEY`) |
| `OBSTACLE_MODEL_DIR` | `weights` | folder of `*.pt` models; **every** model in it runs |
| `OBSTACLE_MODEL_CONF` | 0.25 | per-model confidence floor |
| `OBSTACLE_MATCH_IOU` | 0.4 | mask overlap at which two detections are one obstacle |
| `OBSTACLE_MIN_SCORE` | 0.25 | merged obstacles below this are dropped |
| `OBSTACLE_MAX_ZOOM` | 19 | highest satellite zoom (sharper makes the models read roof texture as obstacles) |
| `OBSTACLE_CROP_MARGIN` | 0.3 | margin around the roof before enlarging |
| `OBSTACLE_ROOF_OVERLAP_MIN` | **0.3** | share of an outline that must be on the roof. The app used 0.5, which discarded large obstacles that straddle the roof edge (measured: on one real roof 0.5 returned nothing, 0.3 returned the obstacle) |
| `OBSTACLE_MIN_AREA_M2` / `OBSTACLE_MAX_AREA_FRACTION` | 0.25 / 0.5 | plausibility limits |
| `OBSTACLE_IMGSZ`, `OBSTACLE_MAX_DET`, `OBSTACLE_DEVICE` | 640 / 50 / cpu | YOLO inference settings |

## Things worth knowing

- **Weights are loaded once** (at startup), so after changing files in `weights/` restart the service. "No models found" is *not* remembered:
  start the service first, copy the weights in, and the next call finds them.
- **The satellite view matters as much as the models.** They were trained on soft Google satellite screenshots; fed anything else (e.g. a sharp
  aerial raster) they find far less. That is why imagery is fetched here and `/detect` takes an outline, not a picture.
- **The roof outline is the limit.** Anything outside it is dropped by design. If the outline sits off the building, obstacles on the real roof
  are lost; compare `dropped_off_roof` in `stats` with how many detections the models made.
- **Static Maps errors never log the key.** Only the exception type is logged.
- The models are single-class, so nothing is typed ("obstacle"). Typing, review/confirm flows and storage belong to the calling application.

## Tests

`python -m pytest` from this folder: fusion, geometry, satellite framing, the `detect()` flow with faked predictions, the API, and a check
that a failed download never leaks the key into the log.

## Provenance

Extracted from `solar-fitness/backend/src/solarfit/providers/{yolo_obstacle_detector,satellite_frame,obstacle_detectors}.py` and the
`yolo_ensemble` block of `rooftop_v1.yaml`, with the `solarfit`/`rasterio` dependencies removed. Same merge rules, framing and filters; the
differences are the 0.3 roof-overlap default, no Solar-API fallback image, and the extra plausibility step being inside `detect()`.
The original code in solar-fitness is unchanged and still what that app runs; pointing it at this service is a separate step.
