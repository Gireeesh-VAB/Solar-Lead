"""add assessments table

Owner: omkar (Scoring, USN & Assessment API) — closes the roadmap's
"Persisted assessments" gap: every assessment is currently computed
fresh and discarded, so there's no history, no cross-site list, no
admin oversight. This table stores exactly what
routers/assessments.py::orchestrate_assessment() already computes — no
new computation, just storage.

owner_org is denormalized from the site at write time (not a join)
so GET /app/admin/assessments and the future customer-scoped listing
can filter without joining sites on every read — the same
denormalization tradeoff sites.py itself makes for owner_org on
vendor_jobs-style tables elsewhere in this schema.

Revision ID: 9f2a7c1e5d84
Revises: b6c1a4f083de
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9f2a7c1e5d84"
down_revision: str | Sequence[str] | None = "b6c1a4f083de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assessments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("site_id", sa.String(), nullable=False),
        sa.Column("owner_org", sa.String(), nullable=False),
        sa.Column("site_type", sa.String(), nullable=False),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("binding_constraint", sa.String(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.String(), nullable=False),
        sa.Column("capacity", sa.JSON(), nullable=False),
        sa.Column("boundary", sa.JSON(), nullable=False),
        sa.Column("usable_area_m2", sa.Float(), nullable=True),
        sa.Column("vision_refinement", sa.JSON(), nullable=True),
        sa.Column("panorama_url", sa.String(), nullable=True),
        sa.Column("ml_suitability_score", sa.Float(), nullable=True),
        sa.Column("ml_model_version", sa.String(), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("reused_from_analysis_id", sa.String(), nullable=True),
        sa.Column("usn", sa.JSON(), nullable=True),
        sa.Column("engine_version", sa.String(), nullable=False),
        sa.Column("constraint_pack_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assessments_site_id", "assessments", ["site_id"])
    op.create_index("ix_assessments_owner_org", "assessments", ["owner_org"])


def downgrade() -> None:
    op.drop_index("ix_assessments_owner_org", table_name="assessments")
    op.drop_index("ix_assessments_site_id", table_name="assessments")
    op.drop_table("assessments")
