"""Owner: Person 2 (Rules Engine).

A narrowly-scoped repository for the one query packs/universal.py's
evacuation_headroom_ceiling (CON-07) needs — nearest substation with
spare capacity, per §14's PostGIS pattern. Deliberately raw SQL via
SQLAlchemy Core rather than a full ORM model: this table has exactly one
consumer and one query, so a mapped class would be pure ceremony.

find_nearest_with_headroom is imported by name into universal.py so
tests can monkeypatch it directly (mirrors providers/weather.py's
testability pattern) — no live database needed for the unit tests that
exercise the ceiling's insufficient_data/ok branching logic. The one
test that exercises the real query lives in tests/test_substations.py
and is skipped when the database isn't reachable.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class NearestSubstation:
    name: str
    spare_capacity_mw: float
    distance_m: float


def find_nearest_with_headroom(session: Session, lat: float, lng: float, limit: int = 5) -> list[NearestSubstation]:
    rows = session.execute(
        text(
            """
            SELECT name,
                   spare_capacity_mw,
                   ST_Distance(location, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography) AS distance_m
            FROM substations
            WHERE spare_capacity_mw > 0
            ORDER BY location <-> ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
            LIMIT :limit
            """
        ),
        {"lat": lat, "lng": lng, "limit": limit},
    ).all()
    return [
        NearestSubstation(name=row.name, spare_capacity_mw=float(row.spare_capacity_mw), distance_m=float(row.distance_m))
        for row in rows
    ]
