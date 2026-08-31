"""ml_tables

Person 4's ML training-sample and model-version tables
(repositories/ml_models.py), backing §9.13 ML Suitability Model
(ML-01..05). No FK to `sites` yet since that table doesn't exist
(Person 1's repositories/sites.py is still a stub).

Revision ID: b7e2d4f8a1c6
Revises: a3f6c8d1e9b4
Create Date: 2026-08-26 20:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e2d4f8a1c6"
down_revision: Union[str, Sequence[str], None] = "a3f6c8d1e9b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ml_training_samples",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("site_id", sa.String(), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("label_source", sa.String(), nullable=False),
        sa.Column("label_value", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ml_training_samples_site_id", "ml_training_samples", ["site_id"])

    op.create_table(
        "ml_model_versions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("version", sa.String(), nullable=False, unique=True),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_list", sa.JSON(), nullable=False),
        sa.Column("hyperparameters", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("artifact_storage_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("group_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_ml_model_versions_status", "ml_model_versions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ml_model_versions_status", table_name="ml_model_versions")
    op.drop_table("ml_model_versions")
    op.drop_index("ix_ml_training_samples_site_id", table_name="ml_training_samples")
    op.drop_table("ml_training_samples")
