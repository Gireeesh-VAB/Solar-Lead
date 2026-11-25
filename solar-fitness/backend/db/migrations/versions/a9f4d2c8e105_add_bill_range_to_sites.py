"""add monthly bill range to sites

CON-05's consumption-offset ceiling has always read
params["annual_consumption_kwh"], and nothing ever supplied it, so on
every assessment to date it returned "insufficient_data" and the
recommended size was capped by roof area alone — which is why a
household comes back at tens of kWp it could never use.

Customers know what they pay, not how many units they used, so the check
form now collects a lowest/highest monthly bill and
engine/consumption.py converts it. These two columns persist what the
customer actually entered rather than the derived figure: the tariff used
for the conversion is a config-pack placeholder that will change, and
re-deriving from the original bill keeps old checks correct when it does.

Both columns are additive and nullable — existing rows and every code
path that does not set them are untouched, and a site without a bill
behaves exactly as it does today.

Revision ID: a9f4d2c8e105
Revises: 57dabc0d79d0
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9f4d2c8e105"
down_revision: str | None = "57dabc0d79d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("monthly_bill_low_inr", sa.Float(), nullable=True))
    op.add_column("sites", sa.Column("monthly_bill_high_inr", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("sites", "monthly_bill_high_inr")
    op.drop_column("sites", "monthly_bill_low_inr")
