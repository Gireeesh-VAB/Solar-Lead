"""Shared foundation piece — built Day 0, real and working.

Backs the async-worker pattern required by VIS-05, VIZ-05, and the
batch path of API-03. Person 3 adds real tasks (vision refinement, 3D
generation) here; Person 1/4 add bulk-import and webhook tasks.

Run a worker with: uv run celery -A solarfit.workers.celery_app worker --loglevel=info
Run the beat scheduler with: uv run celery -A solarfit.workers.celery_app beat --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab

from solarfit.config import get_settings

settings = get_settings()

celery_app = Celery("solarfit", broker=settings.redis_url, backend=settings.redis_url)

# First beat_schedule entry in the project — added by Person 4 for
# USN-06's purge job (workers/tasks_usn.py). Anyone else adding a
# scheduled task appends here rather than starting a second Celery Beat
# config.
celery_app.conf.beat_schedule = {
    "purge-expired-usn-uploads": {
        "task": "solarfit.usn.purge_expired_uploads",
        "schedule": crontab(hour=3, minute=0),
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
    from solarfit.providers.vision import (
        crop_to_boundary,
        fetch_rgb_imagery,
        refine_with_vision_model,
    )

    imagery = fetch_rgb_imagery(lat, lng, radius_meters)
    cropped = crop_to_boundary(imagery, boundary)
    result = refine_with_vision_model(cropped, boundary)
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
