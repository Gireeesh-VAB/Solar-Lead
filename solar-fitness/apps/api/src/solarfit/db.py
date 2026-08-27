"""Shared foundation piece — built Day 0.

The single declarative Base every ORM model in the project attaches to
(Person 1's sites/site_versions tables, Person 3's site_analysis_cache,
Person 4's calibration tables). geoalchemy2 is imported here purely for
its side effect of registering PostGIS-aware column types with
SQLAlchemy, so Alembic's autogenerate recognises `Geometry(...)` columns
correctly.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

import geoalchemy2  # noqa: F401  (side-effect import — registers PostGIS types)
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from solarfit.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    """One pooled engine per process, built from DATABASE_URL."""
    return create_engine(get_settings().database_url, pool_pre_ping=True, future=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope around a series of operations.

    Commits on clean exit, rolls back on any exception. SITE-05's
    "version rather than overwrite" rule depends on the new version row
    and the updated `sites` row landing in the SAME transaction — a
    partial write there would leave a site whose current geometry has no
    corresponding history entry.
    """
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency: `session: Session = Depends(get_session)`."""
    with session_scope() as session:
        yield session
