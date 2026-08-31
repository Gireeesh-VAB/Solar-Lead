"""Shared foundation piece — built Day 0, session factory added Day 1
(by Person 3, first to need it for repositories/analysis_cache.py;
Person 1 reuses the same factory for repositories/sites.py).

The single declarative Base every ORM model in the project attaches to
(Person 1's sites/site_versions tables, Person 3's site_analysis_cache,
Person 4's calibration tables). geoalchemy2 is imported here purely for
its side effect of registering PostGIS-aware column types with
SQLAlchemy, so Alembic's autogenerate recognises `Geometry(...)` columns
correctly.

Two session helpers share the one lazily-created engine/sessionmaker
below: session_scope() (Person 2's minimal addition for
packs/universal.py's evacuation-headroom ceiling — no auto-commit, the
caller manages writes) and get_session() (Person 3's addition for
repositories/analysis_cache.py — commits on clean exit, rolls back on
exception). Pick whichever matches how your repository wants to manage
transactions; both are safe to call even when the database is
unreachable, since the engine is not created until first use.
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
        _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Lazy — creating the engine/session here does not open a DB
    connection until a caller actually executes a query, so this is
    safe to call even when the database is unreachable (the caller is
    responsible for catching the resulting error and degrading
    gracefully, same discipline as providers/weather.py). No auto-commit
    — the caller manages writes."""
    session = _get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def get_session() -> Iterator[Session]:
    """Commits on clean exit, rolls back on exception, always closes.

    Usage: `with get_session() as session: ...`
    """
    session = _get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
