"""merge P1 and P3 migration heads

Revision ID: e612593cce4a
Revises: a9fdffad41ca, 7c2f9d41ab63
Create Date: 2026-08-27 16:02:58.748991

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e612593cce4a'
down_revision: Union[str, Sequence[str], None] = ('a9fdffad41ca', '7c2f9d41ab63')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
