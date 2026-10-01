"""add roof info and vendor survey data columns

Closes part of the "customer -> full site survey -> vendor" gap:
customer-reported roof basics (type/material/slope/construction year) on
`sites`, and the vendor's own in-person obstacle/structural survey
(captured during the field visit, after admin approval) as JSONB on
`vendor_jobs` — same "structured sub-object as JSONB, not a new
normalized table" tradeoff this schema already uses for requirements/
service_area/documents/capacity/vision_refinement.

Revision ID: e5f8a2c1b9d7
Revises: d1a9c4b7e3f5
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f8a2c1b9d7"
down_revision: str | Sequence[str] | None = "d1a9c4b7e3f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("roof_type", sa.String(32), nullable=True))
    op.add_column("sites", sa.Column("roof_material", sa.String(32), nullable=True))
    op.add_column("sites", sa.Column("roof_slope", sa.String(16), nullable=True))
    op.add_column("sites", sa.Column("roof_construction_year", sa.Integer(), nullable=True))

    op.add_column(
        "vendor_jobs",
        sa.Column(
            "obstacle_survey",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "vendor_jobs", sa.Column("structural_assessment", sa.dialects.postgresql.JSONB(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("vendor_jobs", "structural_assessment")
    op.drop_column("vendor_jobs", "obstacle_survey")
    op.drop_column("sites", "roof_construction_year")
    op.drop_column("sites", "roof_slope")
    op.drop_column("sites", "roof_material")
    op.drop_column("sites", "roof_type")
