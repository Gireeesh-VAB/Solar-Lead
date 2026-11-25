"""add import job tables

Owner: karthik (App Platform & Foundation) — persisted, pollable bulk
import runs for the frontend's listImportJobs/getImportJob. The existing
`POST /v1/imports` stays synchronous and untouched; this backs a new,
separate async path (routers/app_imports.py + workers/tasks_imports.py).

import_job_rows is a real FK to import_jobs, unlike calibration_records/
ml_training_samples' plain-string site_id workaround from earlier in this
project's history — sites already existed when this migration was
written, so there's no reason to repeat that pattern here.

Revision ID: b6c8e2a5d713
Revises: a1b7d3e9f204
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6c8e2a5d713"
down_revision: str | Sequence[str] | None = "a1b7d3e9f204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_jobs",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("total_rows", sa.Integer, nullable=False),
        sa.Column("processed_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status in ('queued', 'running', 'partial', 'complete', 'failed')",
            name="ck_import_jobs_status",
        ),
    )

    op.create_table(
        "import_job_rows",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "import_job_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("identifier", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("message", sa.Text, nullable=True),
        sa.CheckConstraint(
            "status in ('success', 'error', 'warning')", name="ck_import_job_rows_status"
        ),
    )
    op.create_index("ix_import_job_rows_import_job_id", "import_job_rows", ["import_job_id"])


def downgrade() -> None:
    op.drop_index("ix_import_job_rows_import_job_id", table_name="import_job_rows")
    op.drop_table("import_job_rows")
    op.drop_table("import_jobs")
