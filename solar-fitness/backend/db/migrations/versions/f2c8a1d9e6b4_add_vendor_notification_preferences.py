"""add vendor notification preferences

Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

Backs the vendor portal's new Settings page — six independent toggles
(new job assignment, job deadline reminders, job reassignment,
submission/payout updates, dispute updates, installation updates), one
JSONB dict rather than six columns, matching vendors.service_area's
existing dict-column convention. Not-null with a server default so
existing vendor rows backfill to "everything on" rather than needing a
separate data migration.

Revision ID: f2c8a1d9e6b4
Revises: d1a4b7c2e903
Create Date: 2026-09-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2c8a1d9e6b4"
down_revision: str | Sequence[str] | None = "d1a4b7c2e903"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFAULT_PREFERENCES = (
    '\'{"newJobAssignment": true, "jobDeadlineReminders": true, '
    '"jobReassignment": true, "submissionAndPayoutUpdates": true, '
    '"disputeUpdates": true, "installationUpdates": true}\'::jsonb'
)


def upgrade() -> None:
    op.add_column(
        "vendors",
        sa.Column(
            "notification_preferences",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text(_DEFAULT_PREFERENCES),
        ),
    )


def downgrade() -> None:
    op.drop_column("vendors", "notification_preferences")
