"""merge keerthana and sameeksha migration heads

Revision ID: 7607752828c6
Revises: 7a4e2c8f9b15, a9f4d2c8e105
Create Date: 2026-09-04 13:02:39.996915

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7607752828c6'
down_revision: Union[str, Sequence[str], None] = ('7a4e2c8f9b15', 'a9f4d2c8e105')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
