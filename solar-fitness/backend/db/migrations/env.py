from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# prepend_sys_path = src in alembic.ini makes these importable.
from solarfit.config import get_settings
from solarfit.db import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the placeholder in alembic.ini with the real DATABASE_URL
# from .env (via solarfit.config.Settings) — one source of truth for
# the connection string, per CFG-01's "no coefficient/constant lives
# in two places" spirit.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Every model attaches to solarfit.db.Base — autogenerate compares
# against this metadata. Import model modules here so they register on
# Base.metadata before autogenerate runs.
from solarfit.repositories import (  # noqa: F401
    audit,
    calibration,
    import_jobs,
    ml_models,
    usn_uploads,
)
from solarfit.repositories import (
    sites as _sites,  # noqa: F401  (registers SiteRow/SiteVersionRow/CompositeSiteRow)
)
from solarfit.repositories import (
    users as _users,  # noqa: F401  (registers UserRow)
)
from solarfit.repositories.analysis_cache import SiteAnalysisCache  # noqa: F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emits SQL without a live DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
