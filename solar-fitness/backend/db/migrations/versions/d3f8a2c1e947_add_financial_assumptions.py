"""add financial_assumptions table

FIN-02. Versioned, admin-editable financial-projection assumptions
(tariff escalation, export rate, self-consumption default, maintenance,
financing defaults) — distinct from packages/config-packs/rooftop_v1.yaml,
which stays the source of truth for FIN-01's own coefficients. Seeds one
initial version (id=1) with the same placeholder defaults
repositories/financial_config.py::DEFAULT_ASSUMPTIONS declares, so the
seed and the Python constant can never drift apart.

Revision ID: d3f8a2c1e947
Revises: f2c8a1d9e6b4
Create Date: 2026-09-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3f8a2c1e947"
down_revision: str | Sequence[str] | None = "f2c8a1d9e6b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    financial_assumptions = op.create_table(
        "financial_assumptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.bulk_insert(
        financial_assumptions,
        [
            {
                "values": {
                    "tariff_escalation_pct_per_year": 3.0,
                    "export_tariff_inr_per_kwh": 3.5,
                    "default_self_consumption_ratio": 0.7,
                    "annual_maintenance_cost_inr_per_kwp": 500.0,
                    "inverter_replacement_year": 12,
                    "inverter_replacement_cost_inr_per_kwp": 8000.0,
                    "financing_default_down_payment_pct": 20.0,
                    "financing_default_interest_rate_pct": 10.5,
                    "financing_default_tenure_years": 5.0,
                },
                "created_by": None,
                "note": "seeded default — FIN-02 Day 0 placeholder values",
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("financial_assumptions")
