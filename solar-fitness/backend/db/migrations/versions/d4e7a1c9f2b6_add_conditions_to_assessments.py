"""add conditions to assessments

Revision ID: d4e7a1c9f2b6
Revises: c1a2f5d8e9b3
Create Date: 2026-09-04 19:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e7a1c9f2b6'
down_revision: str | Sequence[str] | None = 'c1a2f5d8e9b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("assessments", sa.Column("conditions", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("assessments", "conditions")
