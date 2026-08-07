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


def test_missing_required_field_raises_instead_of_defaulting() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, db_host="example.com", db_user="alice")  # db_password missing
