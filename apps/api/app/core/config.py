from pathlib import Path

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

# The .env lives at the repo root (shared with docker compose). We locate it relative
# to this file so it works from any working directory. In Docker/CI there's no file —
# pydantic-settings just falls back to real environment variables.
_API_DIR = Path(__file__).resolve().parents[2]  # apps/api
_REPO_ROOT = _API_DIR.parents[1]  # case-pilot


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_REPO_ROOT / ".env", extra="ignore")

    # e.g. postgresql+psycopg://casepilot:casepilot@localhost:5432/casepilot
    database_url: PostgresDsn


settings = Settings()  # values loaded from env / .env at runtime
