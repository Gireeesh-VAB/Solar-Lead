"""add imagery fields to site_versions

Closes a real gap found during a spec-compliance audit against SITE-04
("persist geometry source, imagery date, imagery quality and geometry
confidence with every boundary") — only geometry_source was actually
captured per version; the other three lived only on the current `sites`
row, so a site's history lost that context the moment a second version
was written. All three columns are additive and nullable; nothing
existing is touched.

Revision ID: e7b3c9a4f2d6
Revises: d4e8f1a7c3b9
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7b3c9a4f2d6"
down_revision: str | Sequence[str] | None = "d4e8f1a7c3b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("site_versions", sa.Column("imagery_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("site_versions", sa.Column("imagery_quality", sa.String(32), nullable=True))
    op.add_column("site_versions", sa.Column("geometry_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("site_versions", "geometry_confidence")
    op.drop_column("site_versions", "imagery_quality")
    op.drop_column("site_versions", "imagery_date")
