"""add previous_vendor_ids to vendor_jobs

Revision ID: f6a9c2e8b4d7
Revises: e5f8b3d1a7c4
Create Date: 2026-09-07 13:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f6a9c2e8b4d7'
down_revision: str | Sequence[str] | None = 'e5f8b3d1a7c4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "vendor_jobs",
        sa.Column(
            "previous_vendor_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("vendor_jobs", "previous_vendor_ids")
