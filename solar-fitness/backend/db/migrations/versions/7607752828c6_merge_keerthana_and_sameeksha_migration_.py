"""merge keerthana and sameeksha migration heads

Revision ID: 7607752828c6
Revises: 7a4e2c8f9b15, a9f4d2c8e105
Create Date: 2026-09-04 13:02:39.996915

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '7607752828c6'
down_revision: str | Sequence[str] | None = ('7a4e2c8f9b15', 'a9f4d2c8e105')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
