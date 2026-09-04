"""merge keerthana and main migration heads

Revision ID: bb0e3ab40254
Revises: 7607752828c6, e8f3a1c6d9b4
Create Date: 2026-09-04 13:29:17.403900

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb0e3ab40254'
down_revision: Union[str, Sequence[str], None] = ('7607752828c6', 'e8f3a1c6d9b4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
