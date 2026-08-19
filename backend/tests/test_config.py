import pytest
from pydantic import ValidationError

from kb_backend.config import Settings


def test_database_url_built_from_fields() -> None:
    settings = Settings(
        _env_file=None,
        db_host="example.com",
        db_port=3306,
        db_user="alice",
        db_password="s3cret",
        db_name="kb",
    )
    url = settings.database_url
    assert url.startswith("mysql+pymysql://")
    assert "alice:s3cret@example.com:3306/kb" in url
    assert "charset=utf8mb4" in url


def test_missing_required_field_raises_instead_of_defaulting(monkeypatch) -> None:
    # conftest 的测试库守卫会把 DB_* 写进进程环境变量（见 conftest 顶部）——
    # 必须先清掉，否则"缺 db_password"会被环境变量默默补上，
    # ValidationError 永远不触发
    for var in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, db_host="example.com", db_user="alice")  # db_password missing
