"""add obstacle tracking columns to site_versions

OBS-04/06 (Person 3, merge-flagged for Person 1's review): records
exactly which obstacle(s) an "obstacle_detection" version's exclusions
change came from, and each one's own GeoJSON polygon, so a later
"obstacle_rejected" version can subtract precisely one of them rather
than reverting the whole batch. Both columns are nullable JSONB —
purely additive, no existing row/column touched.

Revision ID: 4cbd882cb53b
Revises: e612593cce4a
Create Date: 2026-08-27 16:04:24.482274

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4cbd882cb53b'
down_revision: Union[str, Sequence[str], None] = 'e612593cce4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("site_versions", sa.Column("applied_obstacle_ids", postgresql.JSONB(), nullable=True))
    op.add_column("site_versions", sa.Column("applied_obstacle_polygons", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("site_versions", "applied_obstacle_polygons")
    op.drop_column("site_versions", "applied_obstacle_ids")
