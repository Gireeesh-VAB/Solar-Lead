"""Owner: Person 4 (Scoring, USN & Assessment API).

API-03's batch assessment task. orchestrate_assessment/SiteNotFoundError
are imported lazily inside the task body, not at module level — routers/
assessments.py imports run_batch_assessment (for its /batch endpoint),
so a top-level import here would create a circular import. By the time
this task actually runs, routers.assessments is already fully loaded.

Dispatch with:
    from solarfit.workers.tasks_assessments import run_batch_assessment
    run_batch_assessment.delay(["site-1", "site-2"])
"""

from solarfit.workers.celery_app import celery_app


@celery_app.task(name="solarfit.assessments.run_batch_assessment")
def run_batch_assessment(site_ids: list[str]) -> list[dict]:
    """One bad site must never kill the whole batch — each site_id is
    isolated in its own try/except."""
    from solarfit.routers.assessments import SiteNotFoundError, orchestrate_assessment

    results = []
    for site_id in site_ids:
        try:
            response = orchestrate_assessment(site_id)
            results.append({"site_id": site_id, "status": "ok", "result": response.model_dump()})
        except SiteNotFoundError:
            results.append({"site_id": site_id, "status": "not_found"})
        except Exception as e:  # noqa: BLE001 — deliberately broad, see docstring
            results.append({"site_id": site_id, "status": "error", "error": str(e)})
    return results
