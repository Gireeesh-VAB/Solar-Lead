"""Owner: Person 4 (Scoring, USN & Assessment API).

API-03's batch assessment task, plus (Phase 4) the single-check task
backing the customer processing screen's real progress bar.
orchestrate_assessment/SiteNotFoundError are imported lazily inside each
task body, not at module level — routers/assessments.py imports
run_batch_assessment (for its /batch endpoint), so a top-level import
here would create a circular import. By the time a task actually runs,
routers.assessments is already fully loaded.

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


def run_check_assessment(site_id: str, owner_org: str, on_stage) -> dict:
    """The actual work of run_check_assessment_task below, as a plain
    function — kept separate from the @celery_app.task wrapper so tests
    can call it directly (same "task is a thin Celery wrapper around a
    plain, independently-testable function" split repositories/
    calibration.py and engine/fitness.py already use) without needing a
    real broker/worker, matching this codebase's established "tests mock
    .delay() itself rather than running a real worker" discipline (see
    test_analysis_cache.py / test_assessments_router.py's own notes).

    Persistence (assessments_repo.save_assessment) happens HERE rather
    than back in the endpoint that dispatches the task — unlike the old
    synchronous complete_check, there is no HTTP request left open to do
    it in by the time this finishes. Returns a small dict (`{"status":
    ..., ...}`), not the full AssessmentResponse — Celery's result
    backend round-trips through JSON, and the frontend only ever needs
    the outcome status, not the payload (it re-fetches the check via GET
    /app/checks/{id} once told to)."""
    from solarfit.db import session_scope
    from solarfit.providers.validation import GeometryRejected
    from solarfit.repositories import assessments as assessments_repo
    from solarfit.routers.assessments import SiteNotFoundError, orchestrate_assessment

    try:
        response = orchestrate_assessment(site_id, owner_org=owner_org, on_stage=on_stage)
    except SiteNotFoundError as exc:
        return {"status": "not_found", "error": str(exc)}
    except GeometryRejected as exc:
        return {"status": "geometry_rejected", "error": str(exc)}

    with session_scope() as session:
        assessments_repo.save_assessment(session, owner_org=owner_org, **response.model_dump())
        session.commit()

    return {"status": "ok", "site_id": site_id}


@celery_app.task(bind=True, name="solarfit.assessments.run_check_assessment")
def run_check_assessment_task(self, site_id: str, owner_org: str) -> dict:
    """Phase 4 — runs one customer check's assessment as a background job
    instead of blocking the HTTP request that starts it, so the
    processing screen can poll real backend stage progress
    (routers/assessments.py::ASSESSMENT_STAGES) instead of a fake
    client-side timer.

    `self.update_state(state="PROGRESS", ...)` between stages is what
    routers/app_checks.py::get_check_assessment_status reads back via
    `celery_app.AsyncResult(job_id).info` — Celery's own documented
    mechanism for a task to report interim progress, the same shape
    the existing /v1/assessments/batch/{job_id} endpoint already reads
    (`AsyncResult.status`/`.result`), just with an added `meta` payload.
    """

    def on_stage(stage: str) -> None:
        self.update_state(state="PROGRESS", meta={"stage": stage})

    return run_check_assessment(site_id, owner_org, on_stage)
