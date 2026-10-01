"""add competing_buildings_nearby to sites

Revision ID: e5f8b3d1a7c4
Revises: d4e7a1c9f2b6
Create Date: 2026-09-07 12:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5f8b3d1a7c4'
down_revision: str | Sequence[str] | None = 'd4e7a1c9f2b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("sites", sa.Column("competing_buildings_nearby", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sites", "competing_buildings_nearby")
