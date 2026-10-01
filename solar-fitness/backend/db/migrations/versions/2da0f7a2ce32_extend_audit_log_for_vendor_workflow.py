"""extend audit log for vendor workflow

Part of the User -> Vendor -> Super Admin controlled workflow: audit_log
previously carried only actor/action/target/details (a free-text trail).
This adds the structured fields the Super Admin activity screen needs to
filter and diff by (actor identity/role, entity type, cross-references to
the project/survey/customer/vendor involved, and a before/after value
pair), without touching the existing four columns — every current
write_audit_log() call site keeps working unchanged, callers opt into the
richer fields incrementally.

Revision ID: 2da0f7a2ce32
Revises: acf5b6d0f833
Create Date: 2026-09-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2da0f7a2ce32"
down_revision: str | Sequence[str] | None = "acf5b6d0f833"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("actor_id", sa.String(255), nullable=True))
    op.add_column("audit_log", sa.Column("actor_type", sa.String(32), nullable=True))
    op.add_column("audit_log", sa.Column("actor_role", sa.String(32), nullable=True))
    op.add_column("audit_log", sa.Column("entity_type", sa.String(64), nullable=True))
    op.add_column("audit_log", sa.Column("entity_id", sa.String(255), nullable=True))
    op.add_column("audit_log", sa.Column("project_id", sa.String(255), nullable=True))
    op.add_column("audit_log", sa.Column("survey_id", sa.String(255), nullable=True))
    op.add_column("audit_log", sa.Column("customer_id", sa.String(255), nullable=True))
    op.add_column("audit_log", sa.Column("vendor_id", sa.String(255), nullable=True))
    op.add_column("audit_log", sa.Column("previous_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("audit_log", sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("audit_log", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column("audit_log", sa.Column("ip_address", sa.String(64), nullable=True))
    op.add_column("audit_log", sa.Column("user_agent", sa.String(512), nullable=True))

    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"])
    op.create_index("ix_audit_log_project_id", "audit_log", ["project_id"])
    op.create_index("ix_audit_log_survey_id", "audit_log", ["survey_id"])
    op.create_index("ix_audit_log_customer_id", "audit_log", ["customer_id"])
    op.create_index("ix_audit_log_vendor_id", "audit_log", ["vendor_id"])
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_actor_id", table_name="audit_log")
    op.drop_index("ix_audit_log_vendor_id", table_name="audit_log")
    op.drop_index("ix_audit_log_customer_id", table_name="audit_log")
    op.drop_index("ix_audit_log_survey_id", table_name="audit_log")
    op.drop_index("ix_audit_log_project_id", table_name="audit_log")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")

    op.drop_column("audit_log", "user_agent")
    op.drop_column("audit_log", "ip_address")
    op.drop_column("audit_log", "reason")
    op.drop_column("audit_log", "new_value")
    op.drop_column("audit_log", "previous_value")
    op.drop_column("audit_log", "vendor_id")
    op.drop_column("audit_log", "customer_id")
    op.drop_column("audit_log", "survey_id")
    op.drop_column("audit_log", "project_id")
    op.drop_column("audit_log", "entity_id")
    op.drop_column("audit_log", "entity_type")
    op.drop_column("audit_log", "actor_role")
    op.drop_column("audit_log", "actor_type")
    op.drop_column("audit_log", "actor_id")
