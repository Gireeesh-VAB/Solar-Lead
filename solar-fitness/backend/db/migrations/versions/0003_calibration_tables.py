"""calibration_tables

Person 4's calibration tables (repositories/calibration.py), backing
§9.9 Calibration (CAL-01..05). No FK to `sites` yet since that table
doesn't exist (Person 1's repositories/sites.py is still a stub) —
site_id is a plain indexed string for now; add the FK in a later
migration once sites exists.

Revision ID: a3f6c8d1e9b4
Revises: c1a9f0e4b7d2
Create Date: 2026-08-26 19:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f6c8d1e9b4"
down_revision: str | Sequence[str] | None = "c1a9f0e4b7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calibration_records",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("site_id", sa.String(), nullable=False),
        sa.Column("site_type", sa.String(), nullable=False),
        sa.Column("region", sa.String(), nullable=False),
        sa.Column("geometry_source", sa.String(), nullable=True),
        sa.Column("remote_area_m2", sa.Float(), nullable=True),
        sa.Column("measured_area_m2", sa.Float(), nullable=False),
        sa.Column("variance_pct", sa.Float(), nullable=True),
        sa.Column("flagged_superseded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_calibration_records_site_id", "calibration_records", ["site_id"])
    op.create_index("ix_calibration_records_site_type", "calibration_records", ["site_type"])

    op.create_table(
        "utilisation_factor_proposals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("site_type", sa.String(), nullable=False),
        sa.Column("current_factor", sa.Float(), nullable=False),
        sa.Column("proposed_factor", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("based_on_record_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_utilisation_factor_proposals_site_type", "utilisation_factor_proposals", ["site_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_utilisation_factor_proposals_site_type", table_name="utilisation_factor_proposals")
    op.drop_table("utilisation_factor_proposals")
    op.drop_index("ix_calibration_records_site_type", table_name="calibration_records")
    op.drop_index("ix_calibration_records_site_id", table_name="calibration_records")
    op.drop_table("calibration_records")
