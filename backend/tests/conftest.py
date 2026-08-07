from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from kb_backend.config import get_settings
from kb_backend.main import app

BACKEND_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def db_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@pytest.fixture
def alembic_cfg() -> AlembicConfig:
    cfg = AlembicConfig(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return cfg


@pytest.fixture
def migrated_schema(alembic_cfg: AlembicConfig, db_engine: Engine):
    """Bring the real test database to a known state: clean -> head, and always
    clean up back to base afterwards so this test never leaves data behind for
    other issues/tests. Shared across test modules on purpose (see
    docs/specs/2026-08-07-knowledge-base-api-design.md §4): a session-scoped
    "migrate once" variant would be silently broken by any test module that
    unconditionally downgrades to base in its own teardown, so every test that
    needs real tables depends on this same function-scoped fixture instead."""
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")
    try:
        yield
    finally:
        command.downgrade(alembic_cfg, "base")
