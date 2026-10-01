"""add grid/discom feasibility column

Phase 5 of the customer -> full site survey -> vendor/admin workflow.
Spec section 15 "Grid / DISCOM Feasibility" — DISCOM policy/application
tracking (net/gross metering availability, transformer capacity,
approval status) is admin-owned workflow state, not something a
customer or field vendor can determine, so it lives on the assessment
itself (JSONB, same pattern as generation/capacity) rather than sites
or vendor_jobs — it tracks the *this specific assessment's* proposed
capacity against grid capacity, and evolves alongside review_status as
the project moves through approval.

Revision ID: d6b1e9a3c7f2
Revises: c2d8f4a6e9b1
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d6b1e9a3c7f2"
down_revision: str | Sequence[str] | None = "c2d8f4a6e9b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assessments", sa.Column("grid_feasibility", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("assessments", "grid_feasibility")
