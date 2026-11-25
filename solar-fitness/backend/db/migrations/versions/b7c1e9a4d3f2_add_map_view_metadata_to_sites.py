"""add map_view_metadata to sites

Revision ID: b7c1e9a4d3f2
Revises: ad4f9e03fcef
Create Date: 2026-09-08 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b7c1e9a4d3f2'
down_revision: str | Sequence[str] | None = 'ad4f9e03fcef'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("sites", sa.Column("map_view_metadata", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sites", "map_view_metadata")
