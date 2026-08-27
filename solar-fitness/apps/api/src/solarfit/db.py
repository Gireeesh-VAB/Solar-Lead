"""Shared foundation piece — built Day 0.

The single declarative Base every ORM model in the project attaches to
(Person 1's sites/site_versions tables, Person 3's site_analysis_cache,
Person 4's calibration tables). geoalchemy2 is imported here purely for
its side effect of registering PostGIS-aware column types with
SQLAlchemy, so Alembic's autogenerate recognises `Geometry(...)` columns
correctly.

session_scope() below is Person 2's own minimal addition, built because
packs/universal.py's evacuation-headroom ceiling was the first thing
that needed a real DB session — no such pattern existed anywhere before
this. Person 1/Person 3 can adopt or extend it for their own
repositories rather than inventing a second one; it's deliberately
minimal (lazy engine, one sessionmaker) and doesn't touch Base.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import geoalchemy2  # noqa: F401  (side-effect import — registers PostGIS types)
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from solarfit.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def _get_session_factory() -> sessionmaker:
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Lazy — creating the engine/session here does not open a DB
    connection until a caller actually executes a query, so this is
    safe to call even when the database is unreachable (the caller is
    responsible for catching the resulting error and degrading
    gracefully, same discipline as providers/weather.py)."""
    session = _get_session_factory()()
    try:
        yield session
    finally:
        session.close()
