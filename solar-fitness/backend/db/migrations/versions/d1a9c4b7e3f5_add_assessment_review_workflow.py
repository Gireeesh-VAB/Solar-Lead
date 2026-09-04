"""add assessment review workflow

Closes the "Customer -> Feasibility Check -> Admin Review -> Admin
Approval -> Vendor Access" gap: previously routers/app_checks.py::
complete_check() created an unassigned vendor_jobs row straight off the
engine's verdict, with zero admin involvement, and that row was then
unreachable anyway (vendor_id=None, but GET /app/vendor/jobs only ever
returns jobs already scoped to the caller's own vendor_id — no
marketplace view exists). This migration adds a real review gate on the
assessments row itself: review_status starts "pending" for verdicts
that could lead to vendor work (SUITABLE / SUITABLE_SUBJECT_TO_SURVEY)
and "not_applicable" otherwise, an admin explicitly approves (assigning
a specific vendor, which is what actually creates the vendor_jobs row)
or rejects (with a reason), and the resulting vendor_jobs row id is
recorded back on the assessment so the admin UI can link straight to it.

Revision ID: d1a9c4b7e3f5
Revises: 7a4e2c8f9b15
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1a9c4b7e3f5"
down_revision: str | Sequence[str] | None = "7a4e2c8f9b15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessments",
        sa.Column("review_status", sa.String(16), nullable=False, server_default="not_applicable"),
    )
    op.add_column("assessments", sa.Column("reviewed_by", sa.String(255), nullable=True))
    op.add_column("assessments", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assessments", sa.Column("rejection_reason", sa.String(), nullable=True))
    op.add_column(
        "assessments",
        sa.Column("assigned_vendor_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "assessments",
        sa.Column("vendor_job_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_assessments_review_status", "assessments", ["review_status"])

    # Existing rows predate this workflow — backfill using the same
    # eligibility rule new rows get, so nothing already SUITABLE /
    # SUITABLE_SUBJECT_TO_SURVEY silently disappears from the review queue.
    op.execute(
        "UPDATE assessments SET review_status = 'pending' "
        "WHERE verdict IN ('SUITABLE', 'SUITABLE_SUBJECT_TO_SURVEY')"
    )


def downgrade() -> None:
    op.drop_index("ix_assessments_review_status", table_name="assessments")
    op.drop_column("assessments", "vendor_job_id")
    op.drop_column("assessments", "assigned_vendor_id")
    op.drop_column("assessments", "rejection_reason")
    op.drop_column("assessments", "reviewed_at")
    op.drop_column("assessments", "reviewed_by")
    op.drop_column("assessments", "review_status")
