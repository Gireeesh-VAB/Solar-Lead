"""add confidence explainability to assessments

FIT-04 explainability. The customer-facing "Analysis confidence: X%"
figure was a single blended float with no way to show which factors
drove it. engine/fitness.py::_compute_confidence() already computes 5
weighted sub-signals (geometry, imagery_recency, constraint_completeness,
gate_resolution, calibration_state) plus a constraint-specific delta —
these two new columns persist that breakdown and its deterministic,
template-generated explanation sentences, mirroring how score_components
already sits alongside the FIT-01 suitability score.

Revision ID: acf5b6d0f833
Revises: 887412f09dd9
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "acf5b6d0f833"
down_revision: str | Sequence[str] | None = "887412f09dd9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assessments", sa.Column("confidence_components", sa.JSON(), nullable=True))
    op.add_column("assessments", sa.Column("confidence_explanation", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("assessments", "confidence_explanation")
    op.drop_column("assessments", "confidence_components")
