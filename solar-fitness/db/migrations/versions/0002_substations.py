"""substations

Owner: Person 2 (Rules Engine). Creates the substations table
packs/universal.py's evacuation_headroom_ceiling (CON-07) queries for
nearest-substation-with-headroom, per §14's PostGIS pattern.

The five inserted rows are SAMPLE / PLACEHOLDER data only, clustered
near Hyderabad to match this repo's existing test fixtures
(tests/conftest.py's make_site default centroid) — they are not a real
utility substation dataset. Replace with a real import once one is
available; nothing downstream depends on these specific rows beyond
making the nearest-substation query meaningfully testable today.

Revision ID: f3c7a9d21b44
Revises: 9e903dd3f06b
Create Date: 2026-08-27 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3c7a9d21b44"
down_revision: Union[str, Sequence[str], None] = "9e903dd3f06b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE substations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name text NOT NULL,
            location geography(Point, 4326) NOT NULL,
            spare_capacity_mw numeric NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX idx_substations_location ON substations USING GIST (location)")

    # Sample/placeholder rows only — see module docstring.
    op.execute(
        """
        INSERT INTO substations (name, location, spare_capacity_mw) VALUES
            ('Sample Substation - Hyderabad Central', ST_SetSRID(ST_MakePoint(78.4867, 17.3850), 4326)::geography, 5.0),
            ('Sample Substation - Secunderabad', ST_SetSRID(ST_MakePoint(78.4983, 17.4399), 4326)::geography, 2.0),
            ('Sample Substation - Gachibowli', ST_SetSRID(ST_MakePoint(78.3489, 17.4401), 4326)::geography, 0.0),
            ('Sample Substation - LB Nagar', ST_SetSRID(ST_MakePoint(78.5511, 17.3520), 4326)::geography, 8.0),
            ('Sample Substation - Kompally (far, no headroom)', ST_SetSRID(ST_MakePoint(78.4900, 17.5400), 4326)::geography, 0.0)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS substations")
