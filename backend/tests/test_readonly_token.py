"""万能只读 Token 的单测（自管静态凭证，X-Readonly-Token）。

纯逻辑 + TestClient 走 auth_gate 的鉴权拦截路径，全部在进入端点前
返回/拒绝，不碰数据库、不碰统一平台（get_settings 打桩为 unified 模式）。
成功放行路径用 /auth/me 验证——该端点只回显 ContextVar 身份，无 DB 访问。
"""
from __future__ import annotations

import pytest

from kb_backend.auth import deps
from kb_backend.auth.deps import (
    _MIXED_READONLY,
    _READONLY_INVALID,
    _READONLY_WRITE_FORBIDDEN,
    _current_user,
    _readonly_gate,
    get_current_user,
)
from kb_backend.config import Settings
from kb_backend.envelope import BusinessError

TOKEN = "test-readonly-token-123"


@pytest.fixture
def unified_settings(monkeypatch):
    """把 deps 模块的 get_settings 打桩成 unified + 已配置万能只读 Token。
    DB 等必填字段沿用 .env（conftest 已改写为测试库），本文件不会连库。"""
    settings = Settings(auth_mode="unified", readonly_token=TOKEN)
    monkeypatch.setattr(deps, "get_settings", lambda: settings)
    return settings


@pytest.fixture(autouse=True)
def _reset_current_user():
    """直接调用 _readonly_gate 的用例会污染 ContextVar，逐例复位。"""
    yield
    _current_user.set(None)


# ------------------------------------------------------------ 纯逻辑 ----

def test_valid_token_get_sets_readonly_viewer(unified_settings):
    _readonly_gate("GET", "/dimensions", TOKEN)
    user = get_current_user()
    assert user is not None
    assert (user.role, user.auth_source) == ("viewer", "readonly")


def test_invalid_token_rejected_401(unified_settings):
    with pytest.raises(BusinessError) as exc:
        _readonly_gate("GET", "/dimensions", "wrong-token")
    assert exc.value.status_code == 401
    assert _READONLY_INVALID in str(exc.value.message)


def test_unconfigured_feature_rejects_any_token(monkeypatch):
    """READONLY_TOKEN 为空（默认）= 功能关闭，任何值都 401——绝不能出现
    "空配置 + 空串比对通过"的放行。"""
    settings = Settings(auth_mode="unified", readonly_token="")
    monkeypatch.setattr(deps, "get_settings", lambda: settings)
    for candidate in ("", "anything"):
        with pytest.raises(BusinessError) as exc:
            _readonly_gate("GET", "/dimensions", candidate)
        assert exc.value.status_code == 401


def test_write_methods_forbidden_with_explicit_message(unified_settings):
    for method in ("POST", "PATCH", "PUT", "DELETE"):
        with pytest.raises(BusinessError) as exc:
            _readonly_gate(method, "/knowledge-bases", TOKEN)
        assert exc.value.status_code == 403
        assert _READONLY_WRITE_FORBIDDEN in str(exc.value.message)


def test_readonly_surface_matches_viewer_gets(unified_settings):
    """查询面全集：viewer 级 GET 全放行（知识库/知识点/答案/维度/分类等）。"""
    for path in [
        "/dimensions",
        "/admin/dimensions",
        "/knowledge-bases",
        "/knowledge-bases/1/enabled-dimensions",
        "/knowledge-bases/1/dimension-values",
        "/knowledge-bases/1/stats",
        "/knowledge-bases/1/knowledge-points",
        "/knowledge-bases/1/knowledge-points/2",
        "/knowledge-bases/1/knowledge-points/2/resolve",
        "/knowledge-bases/1/knowledge-points/2/answer-groups",
        "/knowledge-bases/1/knowledge-points/2/answers",
        "/knowledge-bases/1/knowledge-points/2/change-log",
        "/knowledge-bases/1/knowledge-points/2/answer-relations",
        "/categories",
        "/change-log",
    ]:
        _readonly_gate("GET", path, TOKEN)


def test_sysadmin_surface_still_denied(unified_settings):
    """/users 是 sysadmin 面：万能只读 Token（viewer）读不到用户名单。"""
    with pytest.raises(BusinessError) as exc:
        _readonly_gate("GET", "/users", TOKEN)
    assert exc.value.status_code == 403


# ------------------------------------------------- auth_gate 集成路径 ----

def test_auth_me_via_readonly_token(unified_settings, client):
    resp = client.get("/auth/me", headers={"X-Readonly-Token": TOKEN})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["role"] == "viewer"
    assert data["auth_source"] == "readonly"


def test_gate_rejects_invalid_token(unified_settings, client):
    resp = client.get("/auth/me", headers={"X-Readonly-Token": "nope"})
    assert resp.status_code == 401


def test_gate_rejects_write_with_valid_token(unified_settings, client):
    resp = client.post(
        "/auth/logout", headers={"X-Readonly-Token": TOKEN}
    )
    assert resp.status_code == 403
    assert _READONLY_WRITE_FORBIDDEN in resp.json()["msg"]


def test_gate_rejects_mixed_credentials(unified_settings, client):
    """万能只读 Token 与任何其他凭证同带 → 400，避免身份混用。"""
    for extra in (
        {"IDENTITYTOKEN": "user-token"},
        {"X-Service-Token": "svc-token"},
    ):
        resp = client.get(
            "/auth/me", headers={"X-Readonly-Token": TOKEN, **extra}
        )
        assert resp.status_code == 400
        assert _MIXED_READONLY in resp.json()["msg"]


def test_gate_users_endpoint_denied(unified_settings, client):
    resp = client.get("/users", headers={"X-Readonly-Token": TOKEN})
    assert resp.status_code == 403
