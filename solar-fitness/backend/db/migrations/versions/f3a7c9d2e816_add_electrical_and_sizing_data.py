"""add electrical connection, consumption, vendor electrical survey, and generation estimate

Phase 2 of the customer -> full site survey -> vendor workflow (Phase 1
was roof info / obstacles / structural assessment). Customer-reported
electrical connection + 12-month consumption history on `sites`, the
vendor's own in-person electrical inspection (spec section 8's physical
half — meter/DB photos, earthing, lightning protection) as JSONB on
`vendor_jobs` (same pattern as structural_assessment), and persisting
the real generation estimate (engine/generation.py's
estimate_generation_kwh()) on `assessments` — it was already computed
on every assessment and silently discarded, never stored or exposed.

Revision ID: f3a7c9d2e816
Revises: e5f8a2c1b9d7
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3a7c9d2e816"
down_revision: str | Sequence[str] | None = "e5f8a2c1b9d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("electricity_board", sa.String(255), nullable=True))
    op.add_column("sites", sa.Column("consumer_number", sa.String(64), nullable=True))
    op.add_column("sites", sa.Column("connection_type", sa.String(16), nullable=True))
    op.add_column("sites", sa.Column("sanctioned_load_kw", sa.Float(), nullable=True))
    op.add_column("sites", sa.Column("contract_demand_kva", sa.Float(), nullable=True))
    op.add_column("sites", sa.Column("connected_load_kw", sa.Float(), nullable=True))
    op.add_column(
        "sites",
        sa.Column(
            "monthly_consumption_kwh",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    op.add_column(
        "vendor_jobs", sa.Column("electrical_assessment", sa.dialects.postgresql.JSONB(), nullable=True)
    )

    op.add_column("assessments", sa.Column("generation", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("assessments", "generation")
    op.drop_column("vendor_jobs", "electrical_assessment")
    op.drop_column("sites", "monthly_consumption_kwh")
    op.drop_column("sites", "connected_load_kw")
    op.drop_column("sites", "contract_demand_kva")
    op.drop_column("sites", "sanctioned_load_kw")
    op.drop_column("sites", "connection_type")
    op.drop_column("sites", "consumer_number")
    op.drop_column("sites", "electricity_board")
