"""Shared foundation piece — built Day 0.

The single declarative Base every ORM model in the project attaches to
(Person 1's sites/site_versions tables, Person 3's site_analysis_cache,
Person 4's calibration tables). geoalchemy2 is imported here purely for
its side effect of registering PostGIS-aware column types with
SQLAlchemy, so Alembic's autogenerate recognises `Geometry(...)` columns
correctly.
"""

import geoalchemy2  # noqa: F401  (side-effect import — registers PostGIS types)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
