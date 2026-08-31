"""§16 Testing — the one test in this suite that touches a real,
running Postgres+PostGIS database (via db.session_scope() + the
0002_substations migration's seeded sample data). Skipped gracefully
when the database isn't reachable, so the rest of the suite (and any
machine without Docker running) is never blocked by this file.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from solarfit import db
from solarfit.repositories.substations import find_nearest_with_headroom

# Matches tests/conftest.py's make_site default centroid and the sample
# rows seeded by db/migrations/versions/0002_substations.py.
HYDERABAD_LAT, HYDERABAD_LNG = 17.3850, 78.4867


@pytest.fixture
def db_session():
    try:
        with db.session_scope() as session:
            session.execute(text("SELECT 1"))
            yield session
    except (OperationalError, ProgrammingError) as exc:
        pytest.skip(f"database not reachable/migrated: {exc}")


def test_nearest_substation_ordering_from_seeded_data(db_session):
    results = find_nearest_with_headroom(db_session, HYDERABAD_LAT, HYDERABAD_LNG, limit=10)

    names = [r.name for r in results]
    assert "Sample Substation - Hyderabad Central" in names
    # Zero-capacity sample rows (Gachibowli, Kompally) must never appear —
    # WHERE spare_capacity_mw > 0 filters them out.
    assert "Sample Substation - Gachibowli" not in names
    assert "Sample Substation - Kompally (far, no headroom)" not in names

    distances = [r.distance_m for r in results]
    assert distances == sorted(distances)  # nearest first
    assert results[0].name == "Sample Substation - Hyderabad Central"


def test_evacuation_headroom_ceiling_end_to_end_against_real_db(db_session, make_site):
    from solarfit.packs.universal import evacuation_headroom_ceiling

    site = make_site()  # centroid defaults to the Hyderabad coordinate above
    ceiling = evacuation_headroom_ceiling(site, params={})

    assert ceiling.status == "ok"
    assert ceiling.ceiling_kwp is not None
    assert ceiling.ceiling_kwp > 0


def test_evacuation_headroom_ceiling_never_crashes_for_a_remote_coordinate(db_session, make_site):
    """The nearest-substation query has no distance cutoff (matching §14's
    reference SQL, which doesn't have one either) — a query from anywhere
    on Earth returns the closest rows with spare capacity, however far.
    True insufficient_data (zero substations with capacity anywhere) is
    covered by the monkeypatched unit test in test_universal_packs.py;
    this test only guards against a crash on an extreme/edge coordinate."""
    from solarfit.packs.universal import evacuation_headroom_ceiling

    far_site = make_site(centroid={"type": "Point", "coordinates": [0.0, 0.0]})
    ceiling = evacuation_headroom_ceiling(far_site, params={})

    assert ceiling.status in {"ok", "insufficient_data"}
