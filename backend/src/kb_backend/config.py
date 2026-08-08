from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

# backend/src/kb_backend/config.py -> backend/.env. Resolved relative to this
# file rather than left as a bare ".env" (which pydantic-settings would
# resolve against the process's current working directory) — otherwise
# running tests/the app from anywhere other than `backend/` silently fails to
# load real config. Found by the Kimi review gate on PR #17.
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    """Application configuration, read from environment variables / a local .env file.

    Required fields have no default on purpose: instantiating Settings() with a
    field missing must raise a validation error instead of silently falling back
    to an empty string (see docs/specs/2026-08-07-backend-skeleton-design.md §6).
    """

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    db_host: str
    db_port: int = 3306
    db_user: str
    db_password: str
    db_name: str = "knowledgebase"
    # Comma-separated origins allowed to call this API cross-origin — the
    # React dev server (issue #6) runs on a different port than the
    # backend, so without this the browser blocks every request outright.
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_allowed_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        return URL.create(
            drivername="mysql+pymysql",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"charset": "utf8mb4"},
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
