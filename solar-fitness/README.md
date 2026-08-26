# Solar Site Fitness & Capacity Engine — Rooftop Backend

Python/FastAPI backend, rooftop-only scope (`ROOFTOP_GOVT` / `ROOFTOP_RESIDENTIAL` /
`ROOFTOP_CI`) — floating/water-body work is on hold. Source of truth:
`Solar_Fitness_Engine_Development_Document_v1.2.pdf` (adds §9.16 Obstacle Detection and
§9.17 Shading Analysis on top of v1.1). Team split and full task breakdown:
`Rooftop_Backend_Implementation_Plan.html` (Desktop).

## Getting started

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```bash
make up        # Postgres+PostGIS and Redis, via infra/docker-compose.yml
make migrate   # alembic upgrade head
make test      # the two real tests that exist on Day 0 (geometry, projection)
make run       # FastAPI dev server — GET /health should return {"status": "ok"}
make worker    # Celery worker — dispatch solarfit.workers.celery_app.ping to check it round-trips
```

No `make` on your machine? Run the underlying commands directly — see the `Makefile`,
they're one line each (`cd apps/api && uv run ...`).

Copy `.env.example` to `.env` and fill in real API keys before you need `providers/solar_api.py`,
`providers/vision.py`, `providers/weather.py`, or `providers/usn_ocr.py` — the scaffold boots
fine with an empty `.env` for everything else.

## Where everything lives

- `apps/api/src/solarfit/domain/` — the frozen shared contracts (`Site`, `ShadingEstimate`,
  `Ceiling`, `Gate`, `CapacityResult`, `AnalysisResult`, `VisionRefinement`, `Obstacle`,
  `PanoramaResult`, `MLScore`). Don't change these without the whole team agreeing — everyone's
  code imports from here.
- `apps/api/src/solarfit/packs/config_pack.py` — the parameter-pack loader. Real coefficients
  live in `packages/config-packs/rooftop_v1.yaml` (currently placeholder values).
- `db/migrations/` — Alembic. `0001_enable_postgis.py` is the only shared migration; your table(s)
  are your own next migration.
- Every other file under `engine/`, `providers/`, `packs/`, `repositories/`, `routers/` that
  isn't listed above is a **stub** with a docstring naming its owner and the exact requirement
  IDs it implements — open your own files below and start there.

## Your slice

### Person 1 — Site & Geometry
§9.1 Site Model, §9.2 Geometry Providers, §9.3 Usable Area, plus the bulk-import/export/auth
slice of §9.8 Interface, plus the extraction half of §9.17 Shading Analysis (`SHADE-01`).

Files: `domain/site.py` (read-only, already frozen), `repositories/sites.py`,
`providers/{base,manual,solar_api,imported}.py`, `engine/area.py`,
`routers/{sites,imports}.py`.

Start with: `repositories/sites.py`'s migration (the `sites` + `site_versions` tables), then
`providers/base.py`'s registry, then the three concrete providers. `providers/solar_api.py`'s
`extract_shading_estimate()` (`SHADE-01`) reuses the same Building Insights response you're
already parsing for the boundary — no new call.

**Done when:** an address can be POSTed, geocoded, resolved via the Solar API, stored with a
versioned boundary, returns a computed usable area, and carries a `ShadingEstimate` (or an
explicit `"unavailable"` one for non-Solar-API geometry sources).

### Person 2 — Rules Engine
§9.4 Constraints, §9.5 Capacity Resolver, §9.6 Generation, §9.10 Configuration, plus the
generation-derate half of §9.17 Shading Analysis (`SHADE-03`).

Files: `packages/config-packs/rooftop_v1.yaml` (tune the placeholder values),
`packs/{universal,rooftop,jurisdictions}.py`, `engine/{resolver,generation}.py`,
`providers/weather.py`.

Start with: tuning `rooftop_v1.yaml`'s real coefficients, then `engine/resolver.py` (port
§12's reference implementation), then the constraint packs. `engine/generation.py`'s shading
derate (`SHADE-03`) reads `site.shading` — already on the frozen `Site` contract — and
`get_shading_derate_factor()` from the config pack.

**Done when:** given a boundary + `usable_area_m2` fixture, the constraint pack evaluates, the
resolver returns capacity + binding constraint + headroom, and generation returns a kWh figure
correctly derated when shading data is present.

### Person 3 — AI Pipeline & Cache
§9.11 Vision Refinement, §9.12 3D Visualization, §9.14 Result Cache, and §9.16 Obstacle
Detection in full (`OBS-01..09`).

Files: `providers/vision.py` (now also the obstacle-detection half, `OBS-01..03`),
`engine/panorama.py`, `engine/obstacles.py` (new — `OBS-04..06`, the auto-apply/reversal half),
`repositories/analysis_cache.py`, `workers/celery_app.py` (extend with real tasks).

Start with: the `site_analysis_cache` migration (see `repositories/analysis_cache.py`'s
docstring for the exact DDL, or §14 of the document), then `round_latlng`/`find_by_key`/`create`,
then `get_or_create_analysis()` per §12.1. `providers/vision.py`'s `refine_with_vision_model()`
returns obstacles in the SAME call as the boundary refinement — don't crop or call the vision-LLM
twice. `engine/obstacles.py` is the one stage in the pipeline that changes `usable_area_m2`
without a human step (`OBS-04`), so build it carefully: it calls back into Person 1's
`repositories.sites.new_boundary_version()` to version the exclusions, then Person 2's
`engine.area.compute_usable_area_m2()` to recompute — reusing their interfaces, not duplicating
them.

**Done when:** a pipeline run produces a stored vision annotation, a structured obstacle list,
and a panorama URL (or explicit `not_generated`); a high-confidence obstacle auto-applies to
exclusions and is reversible by an admin; a second call at the same rounded lat/long returns
instantly with zero external calls.

### Person 4 — Scoring, USN & Assessment API
§9.7 Fitness Scoring, §9.13 ML Suitability Model, §9.15 USN Capture, §9.9 Calibration, plus the
core-assessment slice of §9.8 Interface, plus the scoring half of §9.17 Shading Analysis
(`SHADE-04`).

Files: `engine/{fitness,ml_score}.py`, `providers/usn_ocr.py`, `repositories/calibration.py`,
`routers/assessments.py`.

Start with: `engine/fitness.py` (the authoritative verdict), then `providers/usn_ocr.py`'s
manual-entry path (already given), then the OCR paths. `engine/fitness.py`'s shading
sub-component (`SHADE-04`) reads `site.shading.shading_score` — return `INSUFFICIENT_DATA` for
that sub-component specifically when shading is unavailable, never guess.

**Done when:** given stub fixtures from Person 2 and Person 3, `FIT` and `ML` produce a verdict
+ score independently and testably (including the shading sub-component); USN round-trips
through all three input paths in isolation.

## Coordination points

- **Person 1 ↔ Person 4:** the USN field-group shape (`domain/site.py`'s `UsnCapture`) is
  already frozen — no need to re-agree it, just use it.
- **Person 2 ↔ Person 1 / Person 3:** `packs/config_pack.py`'s loader mechanism is already
  built — Person 1 and Person 3 can call `get_utilisation_factor()` / `get_cache_precision()`
  from day one, even before Person 2 tunes the real values.
- **Person 4's `routers/assessments.py`** is deliberately the last file wired to everyone else's
  real implementations — build it against the domain contracts and mocks first.
- **Person 3 → Person 1 (new):** `engine/obstacles.py`'s auto-apply path (`OBS-04`) calls
  Person 1's `repositories.sites.new_boundary_version()` directly — reuses `SITE-05`'s existing
  versioning rather than a parallel mechanism.
- **Person 3 → Person 2 (new):** after an obstacle auto-applies, `engine/obstacles.py` calls
  Person 2's `engine.area.compute_usable_area_m2()` again — already a pure function, no new
  interface needed.
- **Person 2 → Person 3 (new, config):** `auto_apply_confidence_threshold` lives in Person 2's
  `rooftop_v1.yaml` — Person 3 reads it via `config_pack.get_auto_apply_confidence_threshold()`,
  same pattern as `cache_precision`.
- **Person 1 → Person 2 / Person 4 (new):** `Site.shading` is populated by Person 1
  (`SHADE-01`), consumed by Person 2's generation derate (`SHADE-03`) and Person 4's fitness
  sub-score (`SHADE-04`) — no coordination needed beyond the already-frozen contract, but both
  consumers must handle `source == "unavailable"` as `INSUFFICIENT_DATA`, never a guess.

Full dependency matrix and integration checkpoints: see `Rooftop_Backend_Implementation_Plan.html`.
