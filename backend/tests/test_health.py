from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from kb_backend import db as db_module
from kb_backend.main import app


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"code": 200, "data": {"database": "ok"}, "msg": "操作成功"}


def test_health_db_down_returns_444_envelope_with_500_status(
    client: TestClient, monkeypatch: "pytest.MonkeyPatch"
) -> None:
    class _BrokenSession:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise OperationalError("statement", {}, Exception("connection refused"))

        def close(self) -> None:
            pass

    def _broken_get_db():  # type: ignore[no-untyped-def]
        yield _BrokenSession()

    app.dependency_overrides[db_module.get_db] = _broken_get_db
    try:
        resp = client.get("/health")
    finally:
        app.dependency_overrides.pop(db_module.get_db, None)

    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == 444
    assert body["data"] == {}


def test_unknown_route_returns_envelope(client: TestClient) -> None:
    resp = client.get("/this-route-does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body == {"code": 444, "data": {}, "msg": "Not Found"}


def test_invalid_query_param_returns_envelope_422(client: TestClient) -> None:
    resp = client.get("/health", params={"probe": "not-an-int"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 444
    assert body["data"] == {}
