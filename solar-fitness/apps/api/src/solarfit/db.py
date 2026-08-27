"""Shared foundation piece — built Day 0, session factory added Day 1
(by Person 3, first to need it for repositories/analysis_cache.py;
Person 1 reuses the same factory for repositories/sites.py).

The single declarative Base every ORM model in the project attaches to
(Person 1's sites/site_versions tables, Person 3's site_analysis_cache,
Person 4's calibration tables). geoalchemy2 is imported here purely for
its side effect of registering PostGIS-aware column types with
SQLAlchemy, so Alembic's autogenerate recognises `Geometry(...)` columns
correctly.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import geoalchemy2  # noqa: F401  (side-effect import — registers PostGIS types)
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from solarfit.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def get_session() -> Iterator[Session]:
    """Commits on clean exit, rolls back on exception, always closes.

    Usage: `with get_session() as session: ...`
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
