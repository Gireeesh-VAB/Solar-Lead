"""Owner: Person 4 (Scoring, USN & Assessment API) — API-04's engine_version
source, added as part of routers/assessments.py's response stamping.
Single source of truth is pyproject.toml's own version field, read at
runtime rather than duplicated by hand.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("solarfit")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
