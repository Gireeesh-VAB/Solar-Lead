"""add total_area_m2 and score_components to assessments

Feasibility-report redesign — two real, already-computed values that
were never persisted before: engine/area.py::boundary_area_m2() (the
roof's raw area before setback/exclusions) and engine/fitness.py::
score_fitness()'s own FitnessResult.components (the per-factor
breakdown behind the single blended score). Both additive/nullable so
existing rows read back as None, same pattern as generation/
score_components-adjacent columns already on this table.

Revision ID: adcbefcf0240
Revises: f6a9c2e8b4d7
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "adcbefcf0240"
down_revision: str | Sequence[str] | None = "f6a9c2e8b4d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assessments", sa.Column("total_area_m2", sa.Float(), nullable=True))
    op.add_column("assessments", sa.Column("score_components", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("assessments", "score_components")
    op.drop_column("assessments", "total_area_m2")
