"""Shared foundation piece — built Day 0, real and working.

Backs the async-worker pattern required by VIS-05, VIZ-05, and the
batch path of API-03. Person 3 adds real tasks (vision refinement, 3D
generation) here; Person 1/4 add bulk-import and webhook tasks.

Run a worker with: uv run celery -A solarfit.workers.celery_app worker --loglevel=info
"""

from celery import Celery

from solarfit.config import get_settings

settings = get_settings()

celery_app = Celery("solarfit", broker=settings.redis_url, backend=settings.redis_url)


@celery_app.task(name="solarfit.ping")
def ping() -> str:
    """Proves the worker round-trips end to end. Dispatch with:
    from solarfit.workers.celery_app import ping; ping.delay()
    """
    return "pong"
