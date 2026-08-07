from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    """Application configuration, read from environment variables / a local .env file.

    Required fields have no default on purpose: instantiating Settings() with a
    field missing must raise a validation error instead of silently falling back
    to an empty string (see docs/specs/2026-08-07-backend-skeleton-design.md §6).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_host: str
    db_port: int = 3306
    db_user: str
    db_password: str
    db_name: str = "knowledgebase"

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
