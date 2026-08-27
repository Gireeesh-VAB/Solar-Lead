"""api keys

Person 1 — API-06 (API-key auth dependency + per-tenant rate limiting).

Only a SHA-256 hash of each key is stored; the key itself is shown to the
operator once at creation and never persisted. `prefix` is kept in clear
so a key is identifiable in a UI and revocable without the operator
pasting the secret back in.

Revocation is `revoked_at`, not a delete: an audit trail needs to show
that a key existed and when it stopped working.

Revision ID: 7c2f9d41ab63
Revises: 4b1c7ae02f11
Create Date: 2026-08-27

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7c2f9d41ab63"
down_revision: str | Sequence[str] | None = "4b1c7ae02f11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("owner_org", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        # 64 hex chars = SHA-256. Unique so authentication is an index hit.
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column(
            "rate_limit_per_minute", sa.Integer, nullable=False, server_default="120"
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
        sa.CheckConstraint("rate_limit_per_minute > 0", name="ck_api_keys_rate_limit_positive"),
    )
    op.create_index("ix_api_keys_owner_org", "api_keys", ["owner_org"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_index("ix_api_keys_owner_org", table_name="api_keys")
    op.drop_table("api_keys")
