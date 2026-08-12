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

    # ---- 答案关联(docs/PRD-答案关联.md §7)：向量召回 + LLM 描述生成 ----
    # Both gateways are OpenAI-compatible endpoints (机房 FastGPT/OneAPI →
    # Ollama). All empty by default: the feature degrades to "disabled" —
    # analyze endpoints return a BusinessError and the worker never starts —
    # so an unconfigured deployment is unaffected (PRD §0.11).
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    relation_llm_base_url: str = ""
    relation_llm_api_key: str = ""
    relation_llm_model: str = ""
    relation_top_k: int = 10
    relation_min_similarity: float = 0.60
    relation_embed_batch: int = 32
    relation_gen_batch: int = 10
    relation_max_content_chars: int = 4000

    @property
    def relation_analysis_enabled(self) -> bool:
        """Analysis needs BOTH gateways: embeddings for recall and chat for
        description generation. API key is optional on purpose — an intranet
        gateway may not require one."""
        return bool(
            self.embedding_base_url
            and self.embedding_model
            and self.relation_llm_base_url
            and self.relation_llm_model
        )

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
