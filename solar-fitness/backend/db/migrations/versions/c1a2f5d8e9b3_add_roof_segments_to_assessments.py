"""add roof segments to assessments

Revision ID: c1a2f5d8e9b3
Revises: 8e928263e10b
Create Date: 2026-09-04 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c1a2f5d8e9b3'
down_revision: str | Sequence[str] | None = '8e928263e10b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("assessments", sa.Column("roof_segments", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("assessments", "roof_segments")
