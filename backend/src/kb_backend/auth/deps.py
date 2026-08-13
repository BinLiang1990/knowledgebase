"""全局鉴权依赖（issue #36 设计文档 §3.1）。

装配方式：FastAPI(dependencies=[Depends(auth_gate)]) —— 每个请求先过
auth_gate，由 roles.required_role 的规则表决定要求的最低角色：

- auth_mode=off（本地开发）：直通，注入内置开发者身份（operator 显示
  "admin"，与接入前写死的值一致，行为零变化）。
- auth_mode=unified：读 IDENTITYTOKEN + X-Identity-App-Type，进程内 TTL
  缓存（默认 60s，手册 §6.4——不必每个请求都远程调统一平台）；缓存未命中
  时远程校验并同步身份快照。校验中"认证状态不确定时拒绝请求"（手册
  §6.4），绝不降级放行。

auth_gate 是 async 依赖：ContextVar 在主事件循环任务里设置，随后无论
sync 端点（threadpool 会复制当前 context）还是 async 端点都能读到；
远程校验这种阻塞调用则丢进 run_in_threadpool，不卡事件循环。
"""
from __future__ import annotations

import hashlib
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..envelope import BusinessError
from .roles import required_role, role_at_least
from .sync import sync_identity
from .unified_client import (
    SystemAccessDenied,
    UnifiedAuthError,
    fetch_identity,
    fetch_role_codes,
    normalize_app_type,
)

_NOT_LOGGED_IN = "登录已过期，请重新登录"
_NO_PERMISSION = "暂无权限，请联系系统管理员分配权限"


@dataclass(frozen=True)
class CurrentUser:
    id: int
    display_name: str
    role: str
    auth_source: str  # unified | dev


# off 模式的内置身份：display_name 与接入前写死的 operator="admin" 一致
_DEV_USER = CurrentUser(id=0, display_name="admin", role="sysadmin", auth_source="dev")

_current_user: ContextVar[CurrentUser | None] = ContextVar("kb_current_user", default=None)


def get_current_user() -> CurrentUser | None:
    """当前请求的登录用户；公开路径上（含 off 模式外的豁免面）可能为 None。"""
    return _current_user.get()


def current_operator() -> str:
    """写操作的 operator 落库值：登录用户姓名；无登录上下文时保持历史值
    "admin"（off 模式、以及 worker 线程等非请求上下文）。"""
    user = _current_user.get()
    return user.display_name if user is not None and user.display_name else "admin"


# ---------------------------------------------------- Token 校验 TTL 缓存 ----

_cache_lock = threading.Lock()
_token_cache: dict[str, tuple[float, CurrentUser]] = {}


def invalidate_token_cache() -> None:
    """角色变更(PATCH /users/{id}/role)后调用，让新权限立刻生效。"""
    with _cache_lock:
        _token_cache.clear()


def _cache_key(token: str, app_type: str) -> str:
    # 缓存键用哈希，避免明文 Token 长期驻留内存/意外进日志（手册 §10）
    return hashlib.sha256(f"{app_type}:{token}".encode()).hexdigest()


def _cache_get(key: str) -> CurrentUser | None:
    now = time.monotonic()
    with _cache_lock:
        hit = _token_cache.get(key)
        if hit is None:
            return None
        expires, user = hit
        if expires < now:
            del _token_cache[key]
            return None
        return user


def _cache_put(key: str, user: CurrentUser, ttl: float) -> None:
    now = time.monotonic()
    with _cache_lock:
        # 简单容量保护：缓存只会有"活跃 Token 数"量级的条目，超限全清
        if len(_token_cache) > 1024:
            _token_cache.clear()
        _token_cache[key] = (now + ttl, user)


def _verify_remote(db: Session, token: str, app_type: str) -> CurrentUser:
    """远程校验 + 同步快照（阻塞，调用方负责放进线程池）。"""
    identity = fetch_identity(token, app_type)
    role_codes = fetch_role_codes(token, app_type)
    user = sync_identity(db, identity, role_codes)
    return CurrentUser(
        id=user.id,
        display_name=user.display_name or (user.identity_account or "unknown"),
        role=user.role,
        auth_source="unified",
    )


# ------------------------------------------------------------ 全局依赖 ----

async def auth_gate(request: Request, db: Session = Depends(get_db)) -> None:
    settings = get_settings()

    if not settings.unified_auth_enabled:
        _current_user.set(_DEV_USER)
        return

    minimum = required_role(request.method, request.url.path)
    if minimum is None:
        _current_user.set(None)
        return

    token = (request.headers.get("IDENTITYTOKEN") or "").strip()
    if not token:
        raise BusinessError(_NOT_LOGGED_IN, status_code=401)
    app_type = normalize_app_type(
        request.headers.get("X-Identity-App-Type"), settings.identity_app_type
    )

    key = _cache_key(token, app_type)
    user = _cache_get(key)
    if user is None:
        try:
            user = await run_in_threadpool(_verify_remote, db, token, app_type)
        except SystemAccessDenied as exc:
            raise BusinessError(str(exc), status_code=403) from exc
        except UnifiedAuthError as exc:
            # Token 失效/平台业务失败 → 401 让前端重新登录；
            # 平台不可达同样拒绝（fail-closed），msg 保留原因
            raise BusinessError(str(exc) or _NOT_LOGGED_IN, status_code=401) from exc
        _cache_put(key, user, settings.auth_cache_ttl_seconds)

    _current_user.set(user)

    if not role_at_least(user.role, minimum):
        raise BusinessError(_NO_PERMISSION, status_code=403)
