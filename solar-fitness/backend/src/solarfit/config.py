"""Shared settings, read once from the environment.

Only secrets and connection strings live here. Tunable coefficients
(utilisation factor, cache precision, subsidy rules, etc.) belong in
packages/config-packs/*.yaml per CFG-01 — see packs/config_pack.py.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# solar-fitness/backend/.env, resolved relative to this file rather
# than the process's current working directory — pydantic-settings'
# default env_file=".env" only finds it if the process happens to be
# started from backend/, which isn't the convention here (README says
# `cd backend && uv run ...`). Same fix as packs/config_pack.py's
# _DEFAULT_PACKS_DIR.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    database_url: str = "postgresql+psycopg://solarfit:solarfit@localhost:5432/solarfit"
    redis_url: str = "redis://localhost:6379/0"

    # API-06 escape hatch: accept an X-Owner-Org header instead of a real
    # API key. Local development and the test suite only — it lets any
    # caller claim any tenant, so it must stay false anywhere deployed.
    allow_header_tenant: bool = False

    google_maps_api_key: str = ""
    google_solar_api_key: str = ""
    weather_api_key: str = ""
    openai_api_key: str = ""

    # USN-02/03 — Google Cloud Vision (TEXT_DETECTION) service-account
    # credentials, distinct from the API-key-style GCP settings above.
    google_application_credentials_path: str = ""

    # VIZ-02 artifact storage. "local" writes .glb files to a directory on
    # disk and serves them back through routers/artifacts.py; "s3" uses the
    # object_storage_* settings below. Local is the default so a developer
    # gets working 3D models without any AWS/MinIO credentials at all —
    # same "real working dev default" posture as database_url and
    # jwt_secret above, not a production recommendation.
    object_storage_backend: Literal["local", "s3"] = "local"
    # Deliberately outside src/ and gitignored — generated .glb files are
    # build output, never source.
    local_storage_dir: str = str(_BACKEND_DIR / "var" / "artifacts")
    # Origin the artifact route is reachable at, used to build the URL
    # persisted to panorama_url. Must be whatever the browser can reach,
    # which is why it is configuration rather than a derived value.
    public_base_url: str = "http://localhost:8000"

    object_storage_bucket: str = ""
    object_storage_endpoint_url: str = ""
    object_storage_access_key: str = ""
    object_storage_secret_key: str = ""

    # App-platform auth (auth_users.py) — separate from API-06's tenant-scoped
    # API keys above. Bearer-token login for individual users (customer/
    # vendor/admin), not server-to-server integration.
    # Real (not empty) dev default, unlike the optional external API keys
    # above — auth can't silently no-op when unconfigured the way an
    # unused GPT/Vision integration can. Same category as database_url/
    # redis_url already having real working defaults. Override in any
    # real deployment.
    jwt_secret: str = "dev-insecure-secret-change-in-production"
    jwt_expires_minutes: int = 10080  # 7 days

    # Origins the /app/* web frontend is served from — explicit allowlist,
    # never a wildcard, since bearer tokens are involved.
    cors_allowed_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
