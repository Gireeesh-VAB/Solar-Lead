"""add financial feasibility column

Phase 6 (final phase) of the customer -> full site survey -> vendor/
admin workflow. Spec section 16 "Financial Feasibility" — system cost
breakdown, subsidy, and ROI figures are admin-owned commercial data
(real quotes/negotiated figures, not something the engine computes),
same JSONB-on-assessments pattern as grid_feasibility.

Revision ID: e8f3a1c6d9b4
Revises: d6b1e9a3c7f2
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8f3a1c6d9b4"
down_revision: str | Sequence[str] | None = "d6b1e9a3c7f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assessments", sa.Column("financial_feasibility", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("assessments", "financial_feasibility")
