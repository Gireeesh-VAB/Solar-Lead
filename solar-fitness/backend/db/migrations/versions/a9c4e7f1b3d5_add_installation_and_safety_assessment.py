"""add installation constraints and safety assessment columns

Phase 3 of the customer -> full site survey -> vendor workflow (Phase 1:
roof/obstacles/structural, Phase 2: electrical/consumption/sizing).
Spec sections 12 "Installation Constraints" and 13 "Safety Assessment"
— both entirely vendor-in-person checks (roof/lift access, crane needs,
earthing/isolators/fire equipment), same JSONB-on-vendor_jobs pattern as
structural_assessment/electrical_assessment.

Revision ID: a9c4e7f1b3d5
Revises: f3a7c9d2e816
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9c4e7f1b3d5"
down_revision: str | Sequence[str] | None = "f3a7c9d2e816"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vendor_jobs", sa.Column("installation_constraints", sa.dialects.postgresql.JSONB(), nullable=True)
    )
    op.add_column("vendor_jobs", sa.Column("safety_assessment", sa.dialects.postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("vendor_jobs", "safety_assessment")
    op.drop_column("vendor_jobs", "installation_constraints")
