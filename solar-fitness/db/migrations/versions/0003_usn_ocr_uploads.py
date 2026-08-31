"""usn_ocr_uploads

Person 4's own table (repositories/usn_uploads.py), backing the USN-06
evidence-retention half of §9.15 USN Capture. No FK to `sites` yet since
that table doesn't exist (Person 1's repositories/sites.py is still a
stub) — site_id is a plain indexed string for now; add the FK in a later
migration once sites exists.

Revision ID: c1a9f0e4b7d2
Revises: 9e903dd3f06b
Create Date: 2026-08-26 18:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1a9f0e4b7d2"
down_revision: Union[str, Sequence[str], None] = "9e903dd3f06b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usn_ocr_uploads",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("site_id", sa.String(), nullable=False),
        sa.Column("document_type", sa.String(), nullable=False),
        sa.Column("object_storage_key", sa.String(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extraction_status", sa.String(), nullable=False),
        sa.Column("ocr_raw_text", sa.String(), nullable=True),
        sa.Column("never_use_for_training", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_usn_ocr_uploads_site_id", "usn_ocr_uploads", ["site_id"])
    op.create_index("ix_usn_ocr_uploads_purge_after", "usn_ocr_uploads", ["purge_after"])


def downgrade() -> None:
    op.drop_index("ix_usn_ocr_uploads_purge_after", table_name="usn_ocr_uploads")
    op.drop_index("ix_usn_ocr_uploads_site_id", table_name="usn_ocr_uploads")
    op.drop_table("usn_ocr_uploads")
