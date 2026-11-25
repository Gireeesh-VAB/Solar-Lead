"""add vendor profile fields

Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

Closes the "there is no way to create a vendor" gap — the admin-side
"Add Vendor" flow needs a proper onboarding record (business identity,
contact, address, certifications), not just the payout/service-area
fields the original vendor_domain_tables migration (01c7bb9793b5)
shipped with. All additive and nullable except certifications (defaults
to an empty list, same convention as vendors.documents already uses) —
existing vendor rows are untouched.

Revision ID: b3d9f1a4c672
Revises: 57dabc0d79d0
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3d9f1a4c672"
down_revision: str | Sequence[str] | None = "57dabc0d79d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("vendors", sa.Column("legal_name", sa.String(255), nullable=True))
    op.add_column("vendors", sa.Column("gst_number", sa.String(32), nullable=True))
    op.add_column("vendors", sa.Column("pan_number", sa.String(16), nullable=True))
    op.add_column("vendors", sa.Column("contact_name", sa.String(255), nullable=True))
    op.add_column("vendors", sa.Column("contact_phone", sa.String(32), nullable=True))
    op.add_column("vendors", sa.Column("contact_email", sa.String(255), nullable=True))
    op.add_column("vendors", sa.Column("address_line1", sa.String(255), nullable=True))
    op.add_column("vendors", sa.Column("address_line2", sa.String(255), nullable=True))
    op.add_column("vendors", sa.Column("city", sa.String(128), nullable=True))
    op.add_column("vendors", sa.Column("state", sa.String(128), nullable=True))
    op.add_column("vendors", sa.Column("pincode", sa.String(16), nullable=True))
    op.add_column(
        "vendors",
        sa.Column(
            "certifications",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("vendors", "certifications")
    op.drop_column("vendors", "pincode")
    op.drop_column("vendors", "state")
    op.drop_column("vendors", "city")
    op.drop_column("vendors", "address_line2")
    op.drop_column("vendors", "address_line1")
    op.drop_column("vendors", "contact_email")
    op.drop_column("vendors", "contact_phone")
    op.drop_column("vendors", "contact_name")
    op.drop_column("vendors", "pan_number")
    op.drop_column("vendors", "gst_number")
    op.drop_column("vendors", "legal_name")
