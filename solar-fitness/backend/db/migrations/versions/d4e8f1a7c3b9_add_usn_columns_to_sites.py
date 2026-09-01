"""add usn columns to sites

Closes a real gap found during a spec-compliance audit: USN-01..04
capture (manual entry, bill OCR, payment-proof OCR) all converge on
UsnCapture(usn, usn_source), and POST /sites already validates that
shape via SITE-02's JSON Schema — but `sites` had no column to persist
either value, so a validated USN was silently discarded on every write.
Both columns are additive and nullable; nothing existing is touched.

Revision ID: d4e8f1a7c3b9
Revises: c3f5a9d1e846
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e8f1a7c3b9"
down_revision: str | Sequence[str] | None = "c3f5a9d1e846"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("usn", sa.String(64), nullable=True))
    op.add_column("sites", sa.Column("usn_source", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("sites", "usn_source")
    op.drop_column("sites", "usn")
