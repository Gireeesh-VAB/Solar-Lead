"""add financial_estimate column

FIN-01. engine/financials.py's own computed cost/subsidy/payback
estimate — distinct from the existing financial_feasibility column,
which is an admin-entered real quote. Same JSONB-on-assessments pattern
as generation/financial_feasibility.

Revision ID: c9d2e5f8a1b4
Revises: b7c1e9a4d3f2
Create Date: 2026-09-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d2e5f8a1b4"
down_revision: str | Sequence[str] | None = "b7c1e9a4d3f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assessments", sa.Column("financial_estimate", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("assessments", "financial_estimate")
