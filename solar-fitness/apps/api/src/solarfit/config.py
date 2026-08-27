"""Shared settings, read once from the environment.

Only secrets and connection strings live here. Tunable coefficients
(utilisation factor, cache precision, subsidy rules, etc.) belong in
packages/config-packs/*.yaml per CFG-01 — see packs/config_pack.py.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://solarfit:solarfit@localhost:5432/solarfit"
    redis_url: str = "redis://localhost:6379/0"

    google_maps_api_key: str = ""
    google_solar_api_key: str = ""
    weather_api_key: str = ""
    openai_api_key: str = ""

    # USN-02/03 — Google Cloud Vision (TEXT_DETECTION) service-account
    # credentials, distinct from the API-key-style GCP settings above.
    google_application_credentials_path: str = ""

    object_storage_bucket: str = ""
    object_storage_endpoint_url: str = ""
    object_storage_access_key: str = ""
    object_storage_secret_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
