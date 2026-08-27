"""sites and site_versions

Person 1's first migration — §9.1 Site Model (SITE-01..07), specifically
SITE-05's "version boundary changes rather than overwriting; retain full
history with actor and timestamp."

Two tables:
  sites          current state, one row per site, read path stays single-table
  site_versions  append-only geometry history, never updated or deleted

Geography, not geometry
-----------------------
Every spatial column is `geography(..., 4326)`. ST_Area on a geography
column returns square metres natively, so §17's planar-4326 trap cannot
be reintroduced by a later raw query — the guarantee lives in the schema
rather than only in engine/area.py. Buffering (AREA-03) still projects to
UTM in application code, since a negative buffer wants a true metric CRS.

Deliberately NOT here: `usn`
----------------------------
Site.usn exists on the frozen contract, but USN-06 requires it stored
encrypted at rest with a retention window and hard-excluded from
ML/vision training. Choosing that representation is part of the
requirement and belongs to Person 4 (USN-01..06), so this migration
leaves the column out rather than pre-committing a plaintext JSONB one.
Person 4 adds it in their own migration.

Revision ID: 4b1c7ae02f11
Revises: 9e903dd3f06b
Create Date: 2026-08-25

"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b1c7ae02f11"
down_revision: str | Sequence[str] | None = "9e903dd3f06b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SRID = 4326


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("site_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner_org", sa.String(255), nullable=False),
        sa.Column("jurisdiction", sa.String(32), nullable=False),
        sa.Column(
            "centroid",
            geoalchemy2.Geography("POINT", srid=SRID, spatial_index=False),
            nullable=False,
        ),
        sa.Column(
            "boundary",
            geoalchemy2.Geography("POLYGON", srid=SRID, spatial_index=False),
            nullable=True,
        ),
        sa.Column(
            "exclusions",
            geoalchemy2.Geography("MULTIPOLYGON", srid=SRID, spatial_index=False),
            nullable=True,
        ),
        sa.Column("geometry_source", sa.String(32), nullable=True),
        sa.Column("imagery_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imagery_quality", sa.String(32), nullable=True),
        sa.Column("geometry_confidence", sa.Float, nullable=True),
        sa.Column("shading", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("current_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "site_type IN ('ROOFTOP_GOVT', 'ROOFTOP_RESIDENTIAL', 'ROOFTOP_CI')",
            name="ck_sites_site_type",
        ),
        sa.CheckConstraint(
            "geometry_confidence IS NULL OR (geometry_confidence >= 0 "
            "AND geometry_confidence <= 1)",
            name="ck_sites_geometry_confidence_range",
        ),
    )

    op.create_index("ix_sites_site_type", "sites", ["site_type"])
    op.create_index("ix_sites_owner_org", "sites", ["owner_org"])
    op.create_index("ix_sites_jurisdiction", "sites", ["jurisdiction"])

    # SITE-07 duplicate detection is "is there already a site near this
    # point" — a GiST index on centroid is what makes that a lookup
    # rather than a table scan. Same index serves service-area queries.
    op.create_index("ix_sites_centroid_gist", "sites", ["centroid"], postgresql_using="gist")
    op.create_index("ix_sites_boundary_gist", "sites", ["boundary"], postgresql_using="gist")

    op.create_table(
        "site_versions",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "site_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column(
            "boundary",
            geoalchemy2.Geography("POLYGON", srid=SRID, spatial_index=False),
            nullable=True,
        ),
        sa.Column(
            "exclusions",
            geoalchemy2.Geography("MULTIPOLYGON", srid=SRID, spatial_index=False),
            nullable=True,
        ),
        sa.Column("geometry_source", sa.String(32), nullable=True),
        # SITE-05's "actor and timestamp". `source` is free-form so
        # Person 3 can pass "obstacle_detection" (OBS-04) and
        # "obstacle_rejected" (OBS-06) without a schema change.
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("site_id", "version_no", name="uq_site_versions_site_no"),
        sa.CheckConstraint("version_no > 0", name="ck_site_versions_version_no_positive"),
    )

    op.create_index("ix_site_versions_site_id", "site_versions", ["site_id"])


def downgrade() -> None:
    op.drop_index("ix_site_versions_site_id", table_name="site_versions")
    op.drop_table("site_versions")

    op.drop_index("ix_sites_boundary_gist", table_name="sites")
    op.drop_index("ix_sites_centroid_gist", table_name="sites")
    op.drop_index("ix_sites_jurisdiction", table_name="sites")
    op.drop_index("ix_sites_owner_org", table_name="sites")
    op.drop_index("ix_sites_site_type", table_name="sites")
    op.drop_table("sites")
