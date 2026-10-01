"""Shared foundation piece — built Day 0, real and working.

Backs the async-worker pattern required by VIS-05, VIZ-05, and the
batch path of API-03. Person 3 adds real tasks (vision refinement, 3D
generation) here; Person 1/4 add bulk-import and webhook tasks.

Run a worker with: uv run celery -A solarfit.workers.celery_app worker --loglevel=info
Run the beat scheduler with: uv run celery -A solarfit.workers.celery_app beat --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab
from celery.utils.log import get_task_logger

from solarfit.config import get_settings

settings = get_settings()

celery_app = Celery("solarfit", broker=settings.redis_url, backend=settings.redis_url)

logger = get_task_logger(__name__)

# First beat_schedule entry in the project — added by Person 4 for
# USN-06's purge job (workers/tasks_usn.py). Anyone else adding a
# scheduled task appends here rather than starting a second Celery Beat
# config.
celery_app.conf.beat_schedule = {
    "purge-expired-usn-uploads": {
        "task": "solarfit.usn.purge_expired_uploads",
        "schedule": crontab(hour=3, minute=0),
    },
    # The time-bound lead engine (repositories/vendors.py::
    # sweep_vendor_job_sla(), via workers/tasks_vendors.py). Every 15
    # minutes — frequent enough that a vendor missing a deadline gets
    # flagged/reassigned promptly, infrequent enough not to hammer the
    # DB with a full open-jobs scan.
    "sweep-vendor-sla": {
        "task": "solarfit.vendors.sweep_sla",
        "schedule": crontab(minute="*/15"),
    },
}


@celery_app.task(name="solarfit.ping")
def ping() -> str:
    """Proves the worker round-trips end to end. Dispatch with:
    from solarfit.workers.celery_app import ping; ping.delay()
    """
    return "pong"


@celery_app.task(name="solarfit.vision.refine", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def refine_vision_task(lat: float, lng: float, boundary: dict, radius_meters: float = 25.0) -> dict:
    """VIS-05. Fetches real Solar API RGB imagery, crops to `boundary`,
    runs the GPT-4 Vision refinement call, and returns the result as a
    plain dict (Celery's default JSON serializer can't handle a
    Pydantic model directly). Never raises — refine_with_vision_model()
    itself degrades to an insufficient_data result on any failure
    (VIS-04), so a task failure here would only ever be a genuine bug,
    not an expected external-API hiccup. autoretry_for is a backstop
    for that genuine-bug case, on top of providers/vision.py's own
    with_retries() already covering transient HTTP failures.

    Dispatch with:
        from solarfit.workers.celery_app import refine_vision_task
        refine_vision_task.delay(lat, lng, boundary)
    """
    from solarfit.domain.assessment import VisionRefinement
    from solarfit.providers.obstacle_detectors import detect_obstacles, get_configured_detectors
    from solarfit.providers.vision import (
        crop_to_boundary,
        fetch_rgb_imagery,
        refine_with_vision_model,
    )

    # The docstring above was only ever true of refine_with_vision_model()
    # — the two steps before it could and did raise. No imagery at a
    # location is an ordinary outcome, not a bug: it left the whole
    # assessment 500ing after ~30s of the autoretry backstop retrying a
    # 404 that could never succeed. VIS-04 says degrade to
    # insufficient_data and never block the pipeline, so do that here too.
    try:
        imagery = fetch_rgb_imagery(lat, lng, radius_meters)
        cropped = crop_to_boundary(imagery, boundary)
    except (ValueError, OSError) as exc:
        logger.info("Vision: no usable imagery at (%s, %s) — %s", lat, lng, exc)
        return VisionRefinement(status="insufficient_data").model_dump()

    result = refine_with_vision_model(cropped, boundary)

    # Phase 7 — the pluggable seam (providers/obstacle_detectors.py).
    # get_configured_detectors() returns [] until a second, genuinely
    # independent detector exists, so this is a no-op today; once one is
    # registered, its obstacles merge in here with no other pipeline
    # change (engine/obstacles.py's threshold split already applies
    # uniformly regardless of Obstacle.source).
    extra_detectors = get_configured_detectors()
    if extra_detectors and result.status == "ok":
        result = result.model_copy(
            update={"obstacles": [*result.obstacles, *detect_obstacles(cropped, boundary, detectors=extra_detectors)]}
        )

    return result.model_dump()


@celery_app.task(name="solarfit.obstacles.apply", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def apply_obstacles_task(site_id: str, obstacles: list[dict]) -> dict:
    """OBS-04/05. Looks up the site, applies/flags the just-detected
    obstacles from this site's VisionRefinement, and returns the result
    as plain dicts. `obstacles` are plain dicts (Celery JSON
    serialization) — the caller supplies them, this task doesn't look
    them up itself.

    Dispatch with:
        from solarfit.workers.celery_app import apply_obstacles_task
        apply_obstacles_task.delay(site_id, [o.model_dump() for o in obstacles])
    """
    from solarfit.db import session_scope
    from solarfit.domain.assessment import Obstacle
    from solarfit.engine.obstacles import apply_or_flag
    from solarfit.repositories.sites import get as get_site

    with session_scope() as session:
        site = get_site(session, site_id)
    result = apply_or_flag(site, [Obstacle(**o) for o in obstacles])
    return {"site_id": site_id, "obstacles": [o.model_dump() for o in result]}


@celery_app.task(name="solarfit.panorama.generate", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def generate_panorama_task(boundary: dict, weather: dict | None = None, params: dict | None = None) -> dict:
    """VIZ-05. Runs 3D panorama generation as an async task, chained
    after VIS. Never raises — generate_panorama() itself degrades to a
    not_generated result on any failure (VIZ-03).

    Dispatch with:
        from solarfit.workers.celery_app import generate_panorama_task
        generate_panorama_task.delay(boundary, weather, params)
    """
    from solarfit.engine.panorama import generate_panorama

    result = generate_panorama(boundary, weather, params)
    return result.model_dump()


# Tasks defined in SEPARATE modules only get registered with
# `celery_app` once that module is actually imported. Some FastAPI
# request path importing it transitively (e.g. routers/app_checks.py
# imports tasks_assessments to call .delay()) is enough to make
# DISPATCH work — but a worker started with `celery -A
# solarfit.workers.celery_app worker` only ever imports THIS file, and
# would receive a message for a task it has never heard of (Celery's
# NotRegistered error, the task silently never running). That failure
# mode is exactly as real for a task that's ONLY ever fired by Celery
# Beat's schedule (tasks_usn.py's purge job, tasks_vendors.py's SLA
# sweep — beat only needs the task NAME string to schedule a message;
# the WORKER consuming that message still needs the task registered) as
# for one a request also dispatches — confirmed neither tasks_usn nor
# tasks_vendors was imported anywhere reachable by the worker process
# before this fix, so both had this bug regardless of how they're
# triggered. These imports — after every task above them is already
# registered, so there's nothing left for either to shadow — are what
# make the worker register them too.
from solarfit.workers import (
    tasks_assessments,  # noqa: F401
    tasks_usn,  # noqa: F401
    tasks_vendors,  # noqa: F401
)
