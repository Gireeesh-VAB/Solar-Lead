"""add raised_by_user_id to assessments

Part of the User -> Vendor -> Super Admin controlled workflow: assessments
previously tracked only owner_org (a shared account name, see users.py's
own module docstring) for who raised an enquiry — not enough to notify
the one specific customer who actually submitted it, or to stamp a
customerId on that enquiry's audit-log row. raise_enquiry() sets this
once, the same "first call wins, never overwritten" discipline it already
applies to review_status/customer_selected_vendor_id/enquiry_submitted_at.

No FK to users.id, matching this table's existing no-FK convention (see
AssessmentRow's own module docstring) and every other users.id-shaped
column added elsewhere in this schema.

Revision ID: 56d6f0c69930
Revises: 2da0f7a2ce32
Create Date: 2026-09-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "56d6f0c69930"
down_revision: str | Sequence[str] | None = "2da0f7a2ce32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessments", sa.Column("raised_by_user_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_index("ix_assessments_raised_by_user_id", "assessments", ["raised_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_assessments_raised_by_user_id", table_name="assessments")
    op.drop_column("assessments", "raised_by_user_id")
