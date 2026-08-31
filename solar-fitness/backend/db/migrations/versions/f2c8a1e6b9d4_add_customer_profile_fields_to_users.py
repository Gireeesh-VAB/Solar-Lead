"""add customer profile fields to users

Closes a real gap found while wiring the consumer "checks" self-service
flow: lib/fixtures/customer.ts's CustomerProfile needs `phone` and
`notifyOnComplete`, neither of which exist on `users`. Additive,
nullable/defaulted; nothing existing is touched.

Revision ID: f2c8a1e6b9d4
Revises: 9f2a7c1e5d84
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2c8a1e6b9d4"
down_revision: str | Sequence[str] | None = "9f2a7c1e5d84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(32), nullable=True))
    op.add_column(
        "users",
        sa.Column("notify_on_complete", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("users", "notify_on_complete")
    op.drop_column("users", "phone")
