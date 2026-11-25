"""Owner: karthik (App Platform & Foundation).

Frontend-shaped, async, persisted bulk import — POST /app/imports,
listImportJobs, getImportJob. The existing synchronous POST /v1/imports
(routers/imports.py) is untouched; this is a separate, additive path for
the frontend's "check on a running upload / look back at a past one" UI,
which the synchronous endpoint's one-shot response can't support.

File parsing happens here, synchronously, before the job is created and
the Celery task dispatched — an upload the parser can't make sense of at
all (bad CRS, no rows) is a 422 with nothing to poll for, exactly like
the existing endpoint's own whole-file-failure handling.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, current_user
from solarfit.db import get_session
from solarfit.providers.validation import GeometryRejected
from solarfit.repositories import import_jobs as import_jobs_repo
from solarfit.routers.imports import _rows_from_csv, _rows_from_geometry_file

router = APIRouter(prefix="/app/imports", tags=["app-imports"])


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ImportRowResultOut(_CamelModel):
    row: int
    identifier: str | None
    status: str
    message: str | None = None


class ImportJobOut(_CamelModel):
    id: str
    file_name: str
    status: str
    total_rows: int
    processed_rows: int
    error_rows: int
    created_at: str
    created_by: str
    rows: list[ImportRowResultOut] = []


def _job_out(row, *, include_rows: list | None = None) -> ImportJobOut:
    return ImportJobOut(
        id=str(row.id),
        file_name=row.file_name,
        status=row.status,
        total_rows=row.total_rows,
        processed_rows=row.processed_rows,
        error_rows=row.error_rows,
        created_at=row.created_at.isoformat(),
        created_by=row.created_by,
        rows=[
            ImportRowResultOut(row=r.row_number, identifier=r.identifier, status=r.status, message=r.message)
            for r in (include_rows or [])
        ],
    )


@router.post("", response_model=ImportJobOut, status_code=status.HTTP_201_CREATED)
async def create_import_job(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    file: Annotated[UploadFile, File(description="CSV, GeoJSON, or zipped shapefile")],
    site_type: Annotated[str, Form()] = "ROOFTOP_RESIDENTIAL",
    jurisdiction: Annotated[str, Form()] = "IN-TG",
    source_crs: Annotated[str | None, Form()] = None,
    on_duplicate: Annotated[str, Form()] = "skip",
) -> ImportJobOut:
    """Parses the file synchronously (same parsers the existing sync
    endpoint uses), creates a queued job, dispatches the row-processing
    Celery task, and returns immediately — listImportJobs/getImportJob
    poll from there.

    owner_org for the created sites comes from the caller's own login,
    same as every other /app/* write — a customer importing a portfolio
    only ever creates sites under their own account.
    """
    if not user.owner_org:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only customer accounts can import sites")

    payload = await file.read()
    if not payload:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "uploaded file is empty")

    name = file.filename or ""
    try:
        if name.lower().endswith(".csv"):
            rows = _rows_from_csv(payload)
        else:
            rows = _rows_from_geometry_file(payload, name, source_crs)
    except GeometryRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    job = import_jobs_repo.create_job(
        session, file_name=name, total_rows=len(rows), created_by=user.email
    )

    from solarfit.workers.tasks_imports import run_import_job

    run_import_job.delay(
        str(job.id),
        rows,
        owner_org=user.owner_org,
        site_type=site_type,
        jurisdiction=jurisdiction,
        on_duplicate=on_duplicate,
    )

    return _job_out(job)


@router.get("", response_model=list[ImportJobOut])
def list_import_jobs(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> list[ImportJobOut]:
    """rows omitted here (always []) — matches the frontend's own fixture
    data, which never enumerates every row in the list view either, and
    keeps this endpoint cheap."""
    jobs = import_jobs_repo.list_jobs(session, created_by=user.email)
    return [_job_out(j) for j in jobs]


@router.get("/{job_id}", response_model=ImportJobOut)
def get_import_job(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> ImportJobOut:
    job = import_jobs_repo.get_job(session, job_id)
    if job is None or job.created_by != user.email:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "import job not found")
    rows = import_jobs_repo.list_rows(session, job_id)
    return _job_out(job, include_rows=rows)
