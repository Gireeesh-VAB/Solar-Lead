"""add usn/usn_source to sites

Owner: omkar (Scoring, USN & Assessment API) — closes the gap
sameeksha's sites/site_versions migration deliberately left open:
"Site.usn exists on the frozen contract... Person 4 adds it in their
own migration."

The confirmed usn value is NOT the USN-06 evidence trail (that's
usn_ocr_uploads' encrypted, retention-windowed object storage pointer +
raw OCR text) — it's the final, operator-confirmed value, which lives
with the Site indefinitely since CON-05's subsidy-tier lookup needs it
for the life of the site. Plain nullable columns, additive only.

Revision ID: b6c1a4f083de
Revises: d4e8f2a917b3
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6c1a4f083de"
down_revision: str | Sequence[str] | None = "d4e8f2a917b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("usn", sa.String(length=64), nullable=True))
    op.add_column("sites", sa.Column("usn_source", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("sites", "usn_source")
    op.drop_column("sites", "usn")
