"""add financial_projections table

FIN-02. Persisted snapshots of engine/financial_projection.py's output —
one row per computed projection (never overwritten), each stamping the
financial_assumptions version it was computed against, so a stored
result stays reproducible even after an admin later changes the live
assumptions (spec: "old customer calculations should not silently
change unless explicitly recalculated").

No FK to assessments — same deferred-FK convention already used by
calibration_records/ml_training_samples (see repositories/assessments.py's
own module docstring for why this codebase keeps that convention rather
than mixing FK and non-FK tables).

Revision ID: b6e1c4a9f302
Revises: d3f8a2c1e947
Create Date: 2026-09-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6e1c4a9f302"
down_revision: str | Sequence[str] | None = "d3f8a2c1e947"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_projections",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("assessment_id", sa.String(), nullable=False),
        sa.Column("assumptions_version", sa.Integer(), nullable=False),
        sa.Column("financing_input", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_financial_projections_assessment_id", "financial_projections", ["assessment_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_financial_projections_assessment_id", table_name="financial_projections")
    op.drop_table("financial_projections")
