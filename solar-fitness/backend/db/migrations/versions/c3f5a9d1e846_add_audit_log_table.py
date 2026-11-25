"""add audit log table

Owner: karthik (App Platform & Foundation) — one shared record of every
admin mutation across the /app/* surface (customer suspend/reinstate,
vendor approve/reject, calibration/ML approval, etc.), written via
repositories/audit.py::write_audit_log(). Deliberately its own module,
not inside any router, so omkar's and keerthana's admin routers can call
it without importing karthik's router file.

`details` is a plain string, not JSONB — the frontend's AuditLogEntry
type has `details: string`, a human-readable line, not a structured blob.

Revision ID: c3f5a9d1e846
Revises: b6c8e2a5d713
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3f5a9d1e846"
down_revision: str | Sequence[str] | None = "b6c8e2a5d713"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("target", sa.String(255), nullable=False),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_audit_log_actor", "audit_log", ["actor"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_index("ix_audit_log_actor", table_name="audit_log")
    op.drop_table("audit_log")
