"""测试入口守卫 + 共享 fixtures。

⚠️ 本测试套件对目标数据库是毁灭性的：migrated_schema 会 downgrade base
（drop 全部表）再 upgrade head，目标库里的既有数据每跑一次就清一次。

环境认知（2026-08-19 与用户确认）：RDS 上 `knowledgebase` 是**测试环境**、
`knowledgebase_pro` 才是正式环境（本项目 .env 的账号无权访问 pro）。因此
测试允许指向 `knowledgebase`，但要清楚代价——库里第三方(bqxt)补写的存量
数据会被清掉，重要数据先快照（见备份目录 C:/Users/vibecoding/kb-db-backups）。

守卫规则（_require_isolated_test_database，在导入任何 kb_backend 模块之前
执行）：

- 必须显式配置 TEST_DB_NAME（.env / 环境变量）——没有明确指定测试目标库
  就拒绝启动，防止"随手一跑"清掉当时 DB_NAME 指向的任何库；
- TEST_DB_NAME 含 "pro"（如 knowledgebase_pro）一律拒绝——正式环境绝不
  允许作为测试目标；
- 检查通过后把 DB_* 环境变量整体改写为测试库并清掉 get_settings 缓存，
  之后才 import kb_backend.main——app、引擎、alembic 全部只见测试库。

顺序敏感：kb_backend.main 在模块导入时就会调用 get_settings()（CORS
中间件配置），所以改写必须发生在 import 之前，这也是本文件顶部存在
非常规 import 顺序的原因。
"""

import os

import pytest


def _require_isolated_test_database() -> None:
    from kb_backend.config import Settings, get_settings

    base = Settings()

    test_name = base.test_db_name.strip() or os.getenv("TEST_DB_NAME", "").strip()
    if not test_name:
        pytest.exit(
            "拒绝运行：未配置 TEST_DB_NAME。测试会 drop 目标库的全部表，"
            "必须在 backend/.env 里显式指定测试目标库（当前环境应为 "
            "TEST_DB_NAME=knowledgebase——RDS 上它是测试环境；留空的 "
            "TEST_DB_HOST/USER 等沿用 DB_* 的连接参数）。",
            returncode=1,
        )
    if "pro" in test_name.lower():
        pytest.exit(
            f"拒绝运行：TEST_DB_NAME='{test_name}' 疑似正式环境库"
            "（knowledgebase_pro 是正式库），绝不允许作为测试目标。",
            returncode=1,
        )

    os.environ["DB_HOST"] = base.test_db_host.strip() or base.db_host
    os.environ["DB_PORT"] = str(base.test_db_port or base.db_port)
    os.environ["DB_USER"] = base.test_db_user.strip() or base.db_user
    os.environ["DB_PASSWORD"] = base.test_db_password or base.db_password
    os.environ["DB_NAME"] = test_name
    # get_settings 是 lru_cache——本函数在任何业务代码拿到 Settings 之前
    # 运行，清缓存保证后续所有 get_settings() 都读到上面的测试库覆写
    get_settings.cache_clear()


_require_isolated_test_database()

from pathlib import Path  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

from kb_backend.config import get_settings  # noqa: E402
from kb_backend.main import app  # noqa: E402

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
        # Migration 0002 narrows answer.note (LONGTEXT -> TEXT) on its way
        # down to base; MySQL correctly refuses that ALTER if any row still
        # holds a note over TEXT's 65,535-byte cap. Relying on individual
        # tests to remember to clean up their own oversized rows is a
        # foot-gun — one forgotten cleanup breaks this teardown and cascades
        # into every other test's own setup. Truncate unconditionally before
        # downgrading, regardless of what any given test left behind. Found
        # by the Kimi review gate on PR #20.
        with db_engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE answer"))
        command.downgrade(alembic_cfg, "base")
