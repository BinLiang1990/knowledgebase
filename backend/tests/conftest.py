from pathlib import Path

import pytest
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
