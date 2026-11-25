"""add obstacle_candidates table

Detected-but-not-yet-confirmed rooftop obstacles.

A model detection must not shrink a customer's usable roof until the
customer has looked at it, so detections are held here as `pending`
candidates. Confirming one applies it to the site's exclusions through the
normal SITE-05 versioned path (under the same id); ignoring one keeps the
row as `ignored` so a later re-scan does not offer the same thing again.
`ordinal` is a stable per-site number (#1, #2, ...) that the customer sees
on the map and in the list, and that survives confirmation.

Revision ID: c4a7e1d9b256
Revises: b935e7d7db65
Create Date: 2026-11-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4a7e1d9b256"
down_revision: str | Sequence[str] | None = "b935e7d7db65"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "obstacle_candidates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("polygon", postgresql.JSONB(), nullable=False),
        sa.Column("type", sa.String(32), nullable=False, server_default="other"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="cv_detector"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.UniqueConstraint("site_id", "ordinal", name="uq_obstacle_candidates_site_ordinal"),
    )
    op.create_index("ix_obstacle_candidates_site_id", "obstacle_candidates", ["site_id"])


def downgrade() -> None:
    op.drop_index("ix_obstacle_candidates_site_id", table_name="obstacle_candidates")
    op.drop_table("obstacle_candidates")
