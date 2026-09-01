"""add site domain frontend fields

Owner: karthik (App Platform & Foundation) — closes a real gap found
while building the frontend-shaped site endpoints (routers/app_sites.py):
the frontend's Site type needs address/district/state/tags, and none of
them exist anywhere on `sites` today — POST /sites accepts `address` as
*input* for geocoding but never stores it. All four columns are additive
and nullable; nothing existing is touched.

Also adds `composite_sites` (SITE-06 — feeder/DT aggregation), a new
table entirely, `member_site_ids` deliberately stored as plain JSONB
rather than a join table since group membership here is small and
read-mostly.

Revision ID: a1b7d3e9f204
Revises: f8a3c1d9e6b2
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b7d3e9f204"
down_revision: str | Sequence[str] | None = "f8a3c1d9e6b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("address", sa.String(500), nullable=True))
    op.add_column("sites", sa.Column("district", sa.String(255), nullable=True))
    op.add_column("sites", sa.Column("state", sa.String(255), nullable=True))
    op.add_column(
        "sites",
        sa.Column("tags", sa.dialects.postgresql.JSONB(), nullable=True, server_default="[]"),
    )

    op.create_table(
        "composite_sites",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("feeder_or_dt", sa.String(255), nullable=False),
        sa.Column("member_site_ids", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("composite_sites")
    op.drop_column("sites", "tags")
    op.drop_column("sites", "state")
    op.drop_column("sites", "district")
    op.drop_column("sites", "address")
