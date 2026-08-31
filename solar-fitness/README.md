# Solar Site Fitness & Capacity Engine — Rooftop Backend

Python/FastAPI backend, rooftop-only scope (`ROOFTOP_GOVT` / `ROOFTOP_RESIDENTIAL` /
`ROOFTOP_CI`) — floating/water-body work is on hold. Source of truth:
`Solar_Fitness_Engine_Development_Document_v1.2.pdf` (adds §9.16 Obstacle Detection and
§9.17 Shading Analysis on top of v1.1). Team split and full task breakdown:
`Rooftop_Backend_Implementation_Plan.html` (Desktop).

## Getting started

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```bash
make up        # Postgres+PostGIS and Redis, via backend/infra/docker-compose.yml
make migrate   # alembic upgrade head
make test      # the two real tests that exist on Day 0 (geometry, projection)
make run       # FastAPI dev server — GET /health should return {"status": "ok"}
make worker    # Celery worker — dispatch solarfit.workers.celery_app.ping to check it round-trips
```

No `make` on your machine? Run the underlying commands directly — see the `Makefile`,
they're one line each (`cd backend && uv run ...`).

Copy `.env.example` to `.env` and fill in real API keys before you need `providers/solar_api.py`,
`providers/vision.py`, `providers/weather.py`, or `providers/usn_ocr.py` — the scaffold boots
fine with an empty `.env` for everything else.

## Where everything lives

- `backend/src/solarfit/domain/` — the frozen shared contracts (`Site`, `ShadingEstimate`,
  `Ceiling`, `Gate`, `CapacityResult`, `AnalysisResult`, `VisionRefinement`, `Obstacle`,
  `PanoramaResult`, `MLScore`). Don't change these without the whole team agreeing — everyone's
  code imports from here.
- `backend/src/solarfit/packs/config_pack.py` — the parameter-pack loader. Real coefficients
  live in `backend/packages/config-packs/rooftop_v1.yaml` (currently placeholder values).
- `backend/db/migrations/` — Alembic. `0001_enable_postgis.py` is the only shared migration; your table(s)
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

Files: `backend/packages/config-packs/rooftop_v1.yaml` (tune the placeholder values),
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

**Progress: Day 1 (Result Cache), Day 2 (Vision Refinement), Day 3 (Obstacle Detection), Day 4
(3D Panorama), Day 5 (full-chain wiring + production-hardening), Day 6 (spec-compliance fixes),
and Day 7 (context-mismatch audit fixes) are done — real, tested, 56/56 passing** (including
the 5 DB-integration cache tests). Person 3's slice is feature-complete.

**Day 7 — fixes for places the code was reasoning about, or claiming, more than the actual
available input supports.** Four items, kept independent:
1. The vision prompt asked GPT-4 Vision to note "shading from nearby structures/trees," but
   `crop_to_boundary()` masks everything outside the roof polygon — those structures are never
   in the image the model sees. Reworded to ask for visible shadow evidence on the roof surface
   itself instead of a causal claim about things outside the frame.
2. The 3D panorama now tints the mesh with real per-roof-segment shading — a new
   `providers/vision.py`'s `fetch_building_insights()` (a `buildingInsights:findClosest` call,
   deliberately separate from Person 1's `resolve_via_solar_api()` stub) feeds
   `engine/panorama.py`'s vertex coloring, using each segment's sunshine relative to the
   brightest segment on that same roof. Real Google-computed spatial data, not a vision guess;
   best-effort — any failure exports the mesh uncolored rather than blocking generation.
3. The synthetic `Site` built inline for `apply_or_flag()` had `owner_org`/`jurisdiction` set to
   `"unknown"` — now an unmistakable poison marker instead, so any future code that starts
   reading those fields fails loudly rather than quietly trusting a fake value.
4. CACHE-01's rounding-precision collision risk (two different rooftops close enough together
   could round into the same cache bucket) is now clearly documented in
   `repositories/analysis_cache.py`'s module docstring — a spec-mandated tradeoff, not a P3 bug,
   flagged for the team rather than fixed unilaterally.

**Day 6 — fixes from auditing the full v1.2 spec against the actual code.** Four real gaps
found and closed, all within Person 3's own files:
- Three previously-hardcoded coefficients (`_MIN_OBSTACLE_AREA_M2`, `_MAX_OBSTACLE_AREA_FRACTION_OF_BOUNDARY`
  in `vision.py`; `_GRID_RESOLUTION` in `panorama.py`) moved into `rooftop_v1.yaml` +
  `config_pack.py` accessors — closes a real §17 non-negotiable violation ("no coefficient
  hard-coded").
- `get_or_create_analysis()`'s cache insert had no handling for the `(lat_rounded, lng_rounded)`
  unique-constraint race between two concurrent cache-miss requests for the same location — now
  catches `IntegrityError` and returns the concurrent insert as a hit (CACHE-02/05), instead of
  crashing.
- `reject_applied_obstacle()` now raises a clear, actionable `NotImplementedError` when
  `repositories.sites` isn't real yet, instead of an unlabeled one leaking from a different
  module — deliberately *not* given `apply_or_flag()`'s advisory-only fallback, since there's
  nothing safe to fall back to when reversing a change that was never actually persisted.
- VIZ-04's "regenerate on boundary change" now has a real trigger: a successful (non-degraded)
  `apply_or_flag()` auto-apply calls `force_refresh()` for the site's own location, invalidating
  any stale cached panorama/vision-refinement so the next lookup regenerates.

**Day 5 — obstacle detection is now wired into `get_or_create_analysis()`.** It calls
`engine.obstacles.apply_or_flag()` on the just-detected obstacles before persisting the cache
row, so `.applied` flags are real, not always `False`. Since this cache layer is deliberately
site-independent (`CACHE-01/03` — keyed on lat/long, never on `site_id`), a minimal synthetic
`Site` is built inline just to satisfy `apply_or_flag()`'s signature (it only ever reads
`.id`/`.boundary`/`.exclusions`, so placeholder `name`/`owner_org`/`jurisdiction` values are
inert, never persisted as real site data). `apply_or_flag()`'s auto-apply branch still depends
on Person 1's `repositories/sites.py` (still a stub) — rather than let that crash the pipeline,
it catches `NotImplementedError` from that dependency and falls back to advisory-only, logged,
never silent. Once Person 1 ships `repositories/sites.py` for real, this starts auto-applying
for real with no code change here.

**Day 5 — production-hardening.** `providers/vision.py`'s `with_retries()` (a small,
dependency-free retry loop, reused by `providers/storage.py`) retries Solar API HTTP calls on a
timeout or a 5xx, but never on a 4xx (a bad API key doesn't fix itself on retry #2). The three
Person-3 Celery tasks now carry `autoretry_for`/`retry_backoff` as a backstop for genuine bugs,
on top of `with_retries()` already covering transient HTTP failures.

**Keys still needed for live verification:** `GOOGLE_SOLAR_API_KEY` (imagery, obstacles, DSM
elevation — everything degrades to `insufficient_data`/`not_generated` without it),
`GOOGLE_MAPS_API_KEY`/`WEATHER_API_KEY` (Person 1/2's own stages), and the four
`OBJECT_STORAGE_*` settings (panorama upload — without them `generate_panorama()` always
returns `not_generated`, which is correct behavior, just untested against a real bucket).
`OPENAI_API_KEY` is already set.

**Frontend/API integration — reported, not built here (Person 1/4 + frontend).** `web/` runs
entirely on mock fixtures — zero live HTTP calls anywhere, `NEXT_PUBLIC_API_BASE_URL` referenced
only in a comment. All three backend routers are mounted in `main.py` but have no route
handlers (only `/health` responds). Even once wired, there's a shape mismatch: the frontend's
`Assessment.visionRefinement` type has no `obstacles[]`/`confidence`/`status`, `panoramaUrl` is a
bare string with no `status`/`reason`/`version`, and there's no frontend `Obstacle` type at all.

Files: `providers/vision.py` (real: VIS-01..06 and the OBS-01..03 detection/validation half),
`engine/panorama.py` (real: VIZ-01..05), `providers/storage.py` (new, real: VIZ-02's
object-storage upload), `engine/obstacles.py` (real: OBS-04..06), `repositories/analysis_cache.py`
(real), `repositories/sites.py` (still a stub — `NotImplementedError` bodies, but its interface
now includes the `source`/`exclusions`/`applied_obstacle_ids` params and
`find_version_applying_obstacle()` that `engine/obstacles.py` depends on), `workers/celery_app.py`
(real: `solarfit.ping`, `solarfit.vision.refine`, `solarfit.obstacles.apply`,
`solarfit.panorama.generate`).

**Panorama rendering (Day 4 decision):** no `pyrender`/`Open3D`/OpenGL — `PanoramaResult.url` is
documented only as "a reference URL, the mesh/render artifact lives in object storage," not
specifically a rendered 2D image, so `generate_panorama()` exports a `.glb` 3D mesh (`trimesh`,
pure Python + numpy) for the frontend to render client-side instead. `pyrender`'s offscreen path
needs a GPU or an OSMesa native build, which is fragile-to-unavailable on a plain Windows dev
box — skipping it avoids that risk entirely for a deliverable the frozen contract doesn't
actually require. Elevation comes from the same Solar API Data Layers fetch used for VIS-01
(`fetch_solar_api_datalayers()`'s `dsmUrl`, not a second imagery path); triangulation uses
`shapely.ops.triangulate()` (GEOS-backed, already a dependency) rather than adding `scipy`.
`providers/storage.py` wraps `boto3` against the `object_storage_*` settings (currently empty in
`.env`) — with no endpoint configured it degrades to `PanoramaResult(status="not_generated")`,
never raises, same discipline as VIS-04.

**Obstacle georeferencing (Day 3 decision):** the vision-LLM can't reliably emit precise
lat/lng from pixels (same limitation that keeps `corrected_boundary` at `None`), but an
obstacle is small and well-bounded, so it instead reports a normalized image-fraction bounding
box (0..1, origin top-left) and the server converts that to a real GeoJSON polygon using the
crop's own affine transform — `crop_to_boundary()` now returns a `CroppedImagery` object
(png bytes + transform + CRS + dimensions) instead of raw bytes so that conversion is possible.

**Imagery source (Day 2 decision):** real Google Solar API **Data Layers** (`rgbUrl`, a
georeferenced GeoTIFF), not a plain map screenshot — cropping uses `rasterio`/GDAL against the
image's own embedded geotransform. `rasterio` installs cleanly via `uv add rasterio` (prebuilt
wheel, bundles GDAL — no manual GDAL/OSGeo4W setup needed on Windows). `engine/panorama.py`'s
`VIZ-01` (Day 4) reuses this same fetch/open machinery for its elevation source (`dsmUrl`) — no
second imagery path was built.

`providers/vision.py`'s `refine_with_vision_model()` returns obstacles in the SAME call as the
boundary refinement, as planned — no second crop, no second vision-LLM call.
`engine/obstacles.py` is the one stage in the pipeline that changes `usable_area_m2` without a
human step (`OBS-04`); it's built and tested against Person 1's `repositories.sites` interface
(still `NotImplementedError` bodies) and `engine.area.compute_usable_area_m2()` (still a stub) —
both called for real via lazy import, mocked in tests, same discipline as the Day 1/2 cache
pipeline. Once Person 1 fills in `repositories/sites.py` for real, `apply_or_flag()` and
`reject_applied_obstacle()` need no changes.

Live-call verification: `uv run python -m solarfit.manual_smoke_test_vision` (not part of
`pytest` — real Solar API + OpenAI calls, needs `GOOGLE_SOLAR_API_KEY`/`OPENAI_API_KEY` in
`.env`).

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
