"""add panel layout and boundary warning to assessments

Revision ID: 8e928263e10b
Revises: bb0e3ab40254
Create Date: 2026-09-04 17:25:52.307261

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8e928263e10b'
down_revision: str | Sequence[str] | None = 'bb0e3ab40254'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("assessments", sa.Column("panel_layout", sa.JSON(), nullable=True))
    op.add_column("assessments", sa.Column("boundary_warning", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("assessments", "boundary_warning")
    op.drop_column("assessments", "panel_layout")
