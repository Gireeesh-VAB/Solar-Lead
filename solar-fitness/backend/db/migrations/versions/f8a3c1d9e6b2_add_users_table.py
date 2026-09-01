"""add users table

Owner: karthik (App Platform & Foundation) — individual login for all
three portal roles (customer/vendor/admin), backing the new /app/*
web-app auth surface. Separate from api_keys (API-06's tenant-scoped,
server-to-server auth) — this is bearer-token login for a person.

owner_org is a plain string, the same one sites.owner_org / api_keys.owner_org
already use — it's what connects a customer's login to their sites, not a
new identity space. vendor_id has no FK yet: the vendors table doesn't
exist until a later migration lands (same deferred-FK pattern already used
for site_id on calibration_records/ml_training_samples before
repositories/sites.py existed) — add the FK in a follow-up migration once
vendors does.

Revision ID: f8a3c1d9e6b2
Revises: b7e2d4f8a1c6
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8a3c1d9e6b2"
down_revision: str | Sequence[str] | None = "b7e2d4f8a1c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner_org", sa.String(255), nullable=True),
        sa.Column("tier", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=True, server_default="active"),
        sa.Column("billing_contact_email", sa.String(255), nullable=True),
        sa.Column("vendor_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("role in ('admin', 'customer', 'vendor')", name="ck_users_role"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_owner_org", "users", ["owner_org"])


def downgrade() -> None:
    op.drop_index("ix_users_owner_org", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
