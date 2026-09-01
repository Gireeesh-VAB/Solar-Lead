"""merge P1 and P3 migration heads

Revision ID: e612593cce4a
Revises: a9fdffad41ca, 7c2f9d41ab63
Create Date: 2026-08-27 16:02:58.748991

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = 'e612593cce4a'
down_revision: str | Sequence[str] | None = ('a9fdffad41ca', '7c2f9d41ab63')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
