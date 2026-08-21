"""服务间机器凭证 _service_gate 的单测（X-Service-Token + X-Service-Operator）。

纯逻辑：verify_service_token 打桩为固定平台应答，不碰统一平台、不碰数据库。
直接以构造的 starlette Request 调 _service_gate，断言鉴权拦截与审计身份。
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import Request

from kb_backend.auth import deps
from kb_backend.auth.deps import (
    _SERVICE_FORBIDDEN,
    _SERVICE_OPERATOR_REQUIRED,
    _current_user,
    _decode_operator_header,
    _service_gate,
    current_operator,
    current_source_system,
    get_current_user,
    invalidate_token_cache,
)
from kb_backend.config import Settings
from kb_backend.envelope import BusinessError

TOKEN = "svc-token-under-test"


def _make_request(method: str, path: str, headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "scheme": "http",
        "server": ("testserver", 80),
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [
            (k.lower().encode("latin-1"), v.encode("latin-1"))
            for k, v in (headers or {}).items()
        ],
    }
    return Request(scope)


def _gate(method: str, path: str, headers: dict[str, str] | None = None):
    """跑 _service_gate 并带回 Task 上下文里的身份。

    ContextVar 写入发生在 asyncio.run 的 Task 上下文里，不会传播回测试
    函数（生产环境里端点与鉴权同属一个请求 Task，不存在此问题），所以
    身份断言的取值必须在协程内完成。"""

    async def run():
        await _service_gate(_make_request(method, path, headers), TOKEN)
        return get_current_user(), current_operator(), current_source_system()

    return asyncio.run(run())


@pytest.fixture
def service_env(monkeypatch):
    """unified 模式 + verify_service_token 打桩：Token 有效、来源 yhfkglxt。"""
    settings = Settings(auth_mode="unified")
    monkeypatch.setattr(deps, "get_settings", lambda: settings)

    def fake_verify(token: str):
        assert token == TOKEN
        return {
            "active": True,
            "sourceSystem": fake_verify.source_system,
            "targetSystem": settings.auth_system_code,
            "expiresAt": 0,  # 不缓存，逐测试隔离
        }

    fake_verify.source_system = "yhfkglxt"
    monkeypatch.setattr(deps, "verify_service_token", fake_verify)
    return fake_verify


@pytest.fixture(autouse=True)
def _reset_state():
    yield
    _current_user.set(None)
    invalidate_token_cache()


# ------------------------------------------------------------ 审计留痕 ----

def test_write_without_operator_header_rejected_400(service_env):
    with pytest.raises(BusinessError) as exc:
        _gate("POST", "/knowledge-bases")
    assert exc.value.status_code == 400
    assert _SERVICE_OPERATOR_REQUIRED in str(exc.value.message)


def test_write_with_operator_header_passes_and_stamps_identity(service_env):
    user, operator, source_system = _gate("POST", "/knowledge-bases", {"X-Service-Operator": "zhangsan"})
    assert user is not None
    assert user.auth_source == "service"
    assert user.source_system == "yhfkglxt"
    # 落库 operator = "系统编码:操作人"；source_system = 平台来源系统编码
    assert operator == "yhfkglxt:zhangsan"
    assert source_system == "yhfkglxt"


def test_read_without_operator_header_keeps_system_identity(service_env):
    _user, operator, source_system = _gate("GET", "/knowledge-bases")
    assert operator == "yhfkglxt-service"
    assert source_system == "yhfkglxt"


def test_read_with_operator_header_also_stamped(service_env):
    _user, operator, _source_system = _gate("GET", "/knowledge-bases", {"X-Service-Operator": "lisi"})
    assert operator == "yhfkglxt:lisi"


def test_operator_header_urlencoded_chinese(service_env):
    _user, operator, _source_system = _gate("POST", "/knowledge-bases", {"X-Service-Operator": "%E5%BC%A0%E4%B8%89"})
    assert operator == "yhfkglxt:张三"


def test_current_source_system_defaults_to_own_system(service_env):
    """无鉴权上下文（运营 off 模式 / worker 线程）：source_system = 本系统编码。"""
    _current_user.set(None)
    assert current_source_system() == "tyzsk"


# ------------------------------------------------------------ 白名单 ----

def test_bqxt_write_still_forbidden_even_with_operator(service_env):
    service_env.source_system = "bqxt"
    with pytest.raises(BusinessError) as exc:
        _gate("POST", "/knowledge-bases", {"X-Service-Operator": "zhangsan"})
    assert exc.value.status_code == 403
    assert _SERVICE_FORBIDDEN in str(exc.value.message)


def test_yhfkglxt_out_of_surface_write_forbidden(service_env):
    """开放的是知识库/知识点/答案三块；分类树等仍 403（带了操作人也一样）。"""
    with pytest.raises(BusinessError) as exc:
        _gate("POST", "/categories", {"X-Service-Operator": "zhangsan"})
    assert exc.value.status_code == 403


# ------------------------------------------------------ 头值解码纯逻辑 ----

def test_decode_operator_header_variants():
    # ASCII 原样
    assert _decode_operator_header("zhangsan") == "zhangsan"
    # URL 编码中文（推荐口径）
    assert _decode_operator_header("%E5%BC%A0%E4%B8%89") == "张三"
    # 原始 UTF-8 字节被 starlette 按 latin-1 解出的乱码 → 还原
    assert _decode_operator_header("张三".encode("utf-8").decode("latin-1")) == "张三"
    # 空白与超长截断
    assert _decode_operator_header("  ") == ""
    assert len(_decode_operator_header("a" * 200)) == 80
