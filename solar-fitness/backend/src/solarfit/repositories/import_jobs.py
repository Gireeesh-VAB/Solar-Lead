"""Owner: karthik (App Platform & Foundation).

Persisted, pollable bulk-import runs — backs the frontend's
listImportJobs/getImportJob, which expect a job they can check on while
it's still running and look back at afterward. The existing
`POST /v1/imports` (routers/imports.py) stays synchronous and untouched;
this is a separate, additive path (routers/app_imports.py +
workers/tasks_imports.py), reusing routers/imports.py's own row-processing
logic rather than duplicating it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from solarfit.db import Base

__all__ = [
    "ImportJobRow",
    "ImportJobRowResultRow",
    "create_job",
    "get_job",
    "list_jobs",
    "list_rows",
    "record_row_result",
    "update_job_status",
]


class ImportJobRow(Base):
    __tablename__ = "import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # queued|running|partial|complete|failed
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    rows: Mapped[list[ImportJobRowResultRow]] = relationship(
        back_populates="job", order_by="ImportJobRowResultRow.row_number", cascade="all, delete-orphan"
    )


class ImportJobRowResultRow(Base):
    __tablename__ = "import_job_rows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    import_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # success|error|warning
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped[ImportJobRow] = relationship(back_populates="rows")


def create_job(session: Session, *, file_name: str, total_rows: int, created_by: str) -> ImportJobRow:
    row = ImportJobRow(
        file_name=file_name,
        status="queued",
        total_rows=total_rows,
        processed_rows=0,
        error_rows=0,
        created_by=created_by,
    )
    session.add(row)
    session.flush()
    return row


def get_job(session: Session, job_id: str | uuid.UUID) -> ImportJobRow | None:
    return session.get(ImportJobRow, uuid.UUID(str(job_id)))


def list_jobs(session: Session, *, created_by: str | None = None, limit: int = 100) -> list[ImportJobRow]:
    stmt = select(ImportJobRow).order_by(ImportJobRow.created_at.desc()).limit(limit)
    if created_by is not None:
        stmt = stmt.where(ImportJobRow.created_by == created_by)
    return list(session.scalars(stmt))


def list_rows(session: Session, job_id: str | uuid.UUID) -> list[ImportJobRowResultRow]:
    stmt = (
        select(ImportJobRowResultRow)
        .where(ImportJobRowResultRow.import_job_id == uuid.UUID(str(job_id)))
        .order_by(ImportJobRowResultRow.row_number)
    )
    return list(session.scalars(stmt))


def record_row_result(
    session: Session,
    job_id: str | uuid.UUID,
    *,
    row_number: int,
    status: str,
    identifier: str | None = None,
    message: str | None = None,
) -> ImportJobRowResultRow:
    row = ImportJobRowResultRow(
        import_job_id=uuid.UUID(str(job_id)),
        row_number=row_number,
        identifier=identifier,
        status=status,
        message=message,
    )
    session.add(row)

    job = session.get(ImportJobRow, uuid.UUID(str(job_id)))
    if job is not None:
        job.processed_rows += 1
        if status == "error":
            job.error_rows += 1
    session.flush()
    return row


def update_job_status(session: Session, job_id: str | uuid.UUID, status: str) -> None:
    job = session.get(ImportJobRow, uuid.UUID(str(job_id)))
    if job is not None:
        job.status = status
        session.flush()
