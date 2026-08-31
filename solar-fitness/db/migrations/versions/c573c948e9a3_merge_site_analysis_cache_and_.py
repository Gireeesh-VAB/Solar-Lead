"""merge site_analysis_cache and substations heads

Revision ID: c573c948e9a3
Revises: a9fdffad41ca, f3c7a9d21b44
Create Date: 2026-08-31 11:08:17.205191

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c573c948e9a3'
down_revision: Union[str, Sequence[str], None] = ('a9fdffad41ca', 'f3c7a9d21b44')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
