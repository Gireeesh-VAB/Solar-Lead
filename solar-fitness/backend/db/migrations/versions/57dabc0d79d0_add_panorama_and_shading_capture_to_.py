"""add panorama photo and shading notes capture to vendor_jobs

Additive, nullable columns for a vendor's on-site capture during a
survey job — a photo (stored as a data URL) and free-text shading
notes. Nothing existing is touched.

Revision ID: 57dabc0d79d0
Revises: f2c8a1e6b9d4
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "57dabc0d79d0"
down_revision: str | Sequence[str] | None = "f2c8a1e6b9d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("vendor_jobs", sa.Column("panorama_photo_data_url", sa.Text(), nullable=True))
    op.add_column("vendor_jobs", sa.Column("shading_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("vendor_jobs", "shading_notes")
    op.drop_column("vendor_jobs", "panorama_photo_data_url")
