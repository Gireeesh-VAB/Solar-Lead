"""Owner: karthik (App Platform & Foundation).

Async, persisted bulk import — backs the frontend's listImportJobs/
getImportJob. Reuses routers/imports.py's process_one_row() (the exact
same validation, SITE-07 duplicate check, and savepoint discipline the
existing synchronous POST /v1/imports already uses) rather than
duplicating that logic; only the bookkeeping differs — this writes each
row's outcome to import_job_rows as it goes, instead of building one
in-memory ImportReport.

Dispatch with:
    from solarfit.workers.tasks_imports import run_import_job
    run_import_job.delay(job_id, rows, owner_org=..., site_type=..., jurisdiction=...)

rows/owner_org/etc. are passed in already-parsed (not the raw upload) —
routers/app_imports.py does the file parsing synchronously before
dispatching, since Celery task arguments must be JSON-serializable and a
FastAPI UploadFile isn't. The job row itself is created synchronously too
(so the endpoint can return its id immediately); only row processing runs
in the background.
"""

from solarfit.workers.celery_app import celery_app


@celery_app.task(name="solarfit.imports.run_import_job", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def run_import_job(
    job_id: str,
    rows: list[dict],
    *,
    owner_org: str,
    site_type: str,
    jurisdiction: str,
    on_duplicate: str = "skip",
) -> dict:
    """One bad row must never kill the whole job — process_one_row()
    already isolates each row in its own savepoint; this task isolates
    the bookkeeping around it the same way."""
    from solarfit.db import session_scope
    from solarfit.repositories import import_jobs as import_jobs_repo
    from solarfit.routers.imports import process_one_row

    with session_scope() as session:
        import_jobs_repo.update_job_status(session, job_id, "running")

        for index, row in enumerate(rows, start=1):
            outcome = process_one_row(
                session,
                row,
                index,
                owner_org=owner_org,
                site_type=site_type,
                jurisdiction=jurisdiction,
                on_duplicate=on_duplicate,
            )
            row_status = "success" if outcome.status == "imported" else (
                "warning" if outcome.status == "skipped_duplicate" else "error"
            )
            message = (
                outcome.error.reason
                if outcome.error
                else (f"duplicate of {outcome.duplicate.existing_site_id}" if outcome.duplicate else None)
            )
            import_jobs_repo.record_row_result(
                session,
                job_id,
                row_number=index,
                status=row_status,
                identifier=outcome.row_name,
                message=message,
            )

        job = import_jobs_repo.get_job(session, job_id)
        final_status = "complete" if job and job.error_rows == 0 else "partial"
        import_jobs_repo.update_job_status(session, job_id, final_status)

    return {"job_id": job_id, "status": final_status}
