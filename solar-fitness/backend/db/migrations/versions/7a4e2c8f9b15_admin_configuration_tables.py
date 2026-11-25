"""admin configuration tables

Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

Closes the "Configuration page's feature flags and API keys are
hardcoded arrays with no backend" gap. feature_flags backs the toggle
switches on AdminConfigurationClient.tsx; service_api_keys backs its
masked-key list and the existing /app/admin/api-keys/rotate endpoint
(which previously only wrote an audit-log entry with nothing to
persist against). Both tables are seeded here with the exact rows the
frontend's own FEATURE_FLAGS/MASKED_KEYS constants already hardcoded,
so this migration is a lossless move from "hardcoded in the client" to
"a real, editable row" rather than a behavior change.

Revision ID: 7a4e2c8f9b15
Revises: b3d9f1a4c672
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a4e2c8f9b15"
down_revision: str | Sequence[str] | None = "b3d9f1a4c672"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    feature_flags = op.create_table(
        "feature_flags",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("key", name="uq_feature_flags_key"),
    )
    op.create_index("ix_feature_flags_key", "feature_flags", ["key"], unique=True)

    service_api_keys = op.create_table(
        "service_api_keys",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("service", sa.String(255), nullable=False),
        sa.Column("masked_value", sa.String(64), nullable=False),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("service", name="uq_service_api_keys_service"),
    )
    op.create_index("ix_service_api_keys_service", "service_api_keys", ["service"], unique=True)

    op.bulk_insert(
        feature_flags,
        [
            {
                "key": "vision_refinement",
                "label": "Vision-based boundary refinement",
                "description": "Enable panorama-driven boundary corrections during assessment.",
                "enabled": True,
            },
            {
                "key": "composite_sites",
                "label": "Composite site aggregation",
                "description": "Allow grouping sites under a shared feeder/DT for aggregate capacity.",
                "enabled": True,
            },
            {
                "key": "usn_ocr",
                "label": "USN OCR extraction",
                "description": "Extract unique service numbers from uploaded bills automatically.",
                "enabled": False,
            },
            {
                "key": "vendor_marketplace",
                "label": "Vendor marketplace v2",
                "description": "New job-matching algorithm for vendor assignment.",
                "enabled": False,
            },
        ],
    )

    op.bulk_insert(
        service_api_keys,
        [
            {"service": "Google Maps API", "masked_value": "AIza••••••••••••7Qk2"},
            {"service": "Solar API", "masked_value": "sol_live_••••••••9f3a"},
            {"service": "Vision API", "masked_value": "vis_live_••••••••c81d"},
            {"service": "Weather API", "masked_value": "wx_live_••••••••4b7e"},
        ],
    )


def downgrade() -> None:
    op.drop_table("service_api_keys")
    op.drop_table("feature_flags")
