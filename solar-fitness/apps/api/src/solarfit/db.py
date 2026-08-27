"""Shared foundation piece — built Day 0, session helper added by Person 4
alongside the first real repository code in the project (repositories/
usn_uploads.py) since nobody else had needed one yet. Any other
repository (Person 1's sites.py, Person 3's analysis_cache.py) should
reuse get_session() rather than build a second engine.

The single declarative Base every ORM model in the project attaches to
(Person 1's sites/site_versions tables, Person 3's site_analysis_cache,
Person 4's calibration/usn_ocr_uploads tables). geoalchemy2 is imported
here purely for its side effect of registering PostGIS-aware column
types with SQLAlchemy, so Alembic's autogenerate recognises
`Geometry(...)` columns correctly.
"""

from functools import lru_cache

import geoalchemy2  # noqa: F401  (side-effect import — registers PostGIS types)
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from solarfit.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine():
    return create_engine(get_settings().database_url)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine())


def get_session() -> Session:
    """Use as a context manager: `with get_session() as session: ...`.
    Caller is responsible for committing — nothing here auto-commits."""
    return _session_factory()()
