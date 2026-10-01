"""add consumption kwh to sites

FIN-03. The customer's own lowest/highest monthly electricity
consumption in kWh — the PRIMARY input for seasonal consumption
estimation (engine/seasonal_consumption.py), kept as a separate pair
from the existing monthly_bill_low_inr/monthly_bill_high_inr (₹, still
supported as a fallback when a customer only knows their bill amount,
never used to derive solar sizing directly).

Revision ID: e7c4a9f1b3d6
Revises: b6e1c4a9f302
Create Date: 2026-09-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7c4a9f1b3d6"
down_revision: str | Sequence[str] | None = "b6e1c4a9f302"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("highest_consumption_kwh", sa.Float(), nullable=True))
    op.add_column("sites", sa.Column("lowest_consumption_kwh", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("sites", "lowest_consumption_kwh")
    op.drop_column("sites", "highest_consumption_kwh")
