"""add changelog to ml_model_versions

Owner: omkar (Scoring, USN & Assessment API) — closes the roadmap's
"ModelVersionProposal.changelog has no backend field at all" gap.
Additive, nullable — no existing column touched.

Revision ID: d4e8f2a917b3
Revises: f8a3c1d9e6b2
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e8f2a917b3"
down_revision: str | Sequence[str] | None = "f8a3c1d9e6b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ml_model_versions", sa.Column("changelog", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("ml_model_versions", "changelog")
