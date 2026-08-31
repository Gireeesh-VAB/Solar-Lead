"""enable postgis

The one migration that's genuinely foundational rather than any single
person's — enables the extensions every later migration depends on.
Person 1's `sites`/`site_versions` tables and Person 3's
`site_analysis_cache` table are their own first tasks, deliberately not
created here.

Revision ID: 9e903dd3f06b
Revises:
Create Date: 2026-08-24 17:57:05.098292

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e903dd3f06b"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
    op.execute("DROP EXTENSION IF EXISTS postgis")
