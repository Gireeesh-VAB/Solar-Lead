"""add notifications table

Owner: karthik (App Platform & Foundation).

In-app notifications — vendors already had toggle-only preference fields
(vendors.notification_preferences, users.notify_on_complete) with no
actual send mechanism behind them. This table plus
repositories/notifications.py is that mechanism: a synchronous DB write
at each triggering call site (assessment approval/reassignment, SLA
sweep, job submission), same "write at the call site, no queue" shape as
repositories/audit.py::write_audit_log(). No FK to users.id — no FK
exists to that table anywhere yet (see repositories/users.py's own
module docstring on why), kept consistent rather than mixing FK and
non-FK conventions across this table's own column and every other
users.id-referencing column already in this schema.

Revision ID: 887412f09dd9
Revises: e7c4a9f1b3d6
Create Date: 2026-09-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "887412f09dd9"
down_revision: str | Sequence[str] | None = "e7c4a9f1b3d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
