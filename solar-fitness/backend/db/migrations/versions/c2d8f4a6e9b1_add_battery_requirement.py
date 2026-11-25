"""add battery requirement fields

Phase 4 of the customer -> full site survey -> vendor workflow. Spec
section 14 "Battery Requirement" splits the same way every prior
section has: what the customer wants (battery/backup interest, required
backup hours, critical loads — self-reported at check creation, on
`sites`) vs. what only a vendor standing in the building can assess and
recommend (battery room/location/ventilation/fire safety, plus their
own capacity/technology recommendation from the actual site — JSONB on
`vendor_jobs`, same pattern as structural_assessment etc.).

Revision ID: c2d8f4a6e9b1
Revises: a9c4e7f1b3d5
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d8f4a6e9b1"
down_revision: str | Sequence[str] | None = "a9c4e7f1b3d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("battery_required", sa.Boolean(), nullable=True))
    op.add_column("sites", sa.Column("backup_required", sa.Boolean(), nullable=True))
    op.add_column("sites", sa.Column("required_backup_hours", sa.Float(), nullable=True))
    op.add_column("sites", sa.Column("critical_loads", sa.String(), nullable=True))

    op.add_column("vendor_jobs", sa.Column("battery_assessment", sa.dialects.postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("vendor_jobs", "battery_assessment")
    op.drop_column("sites", "critical_loads")
    op.drop_column("sites", "required_backup_hours")
    op.drop_column("sites", "backup_required")
    op.drop_column("sites", "battery_required")
