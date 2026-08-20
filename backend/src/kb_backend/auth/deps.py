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
import secrets
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
from .roles import THIRD_PARTY_EXEMPT, required_role, role_at_least, service_source_allowed
from .sync import sync_identity
from .unified_client import (
    SystemAccessDenied,
    UnifiedAuthError,
    fetch_identity,
    fetch_role_codes,
    normalize_app_type,
    verify_service_token,
)

_NOT_LOGGED_IN = "登录已过期，请重新登录"
_NO_PERMISSION = "暂无权限，请联系系统管理员分配权限"
_MIXED_TOKENS = "请求不能同时携带用户 Token 与服务 Token"
_SERVICE_INVALID = "服务凭证无效或已过期"
_SERVICE_FORBIDDEN = "该来源系统无权访问此接口"
_SERVICE_REQUIRED = "本接口需携带服务凭证（X-Service-Token）"
_READONLY_INVALID = "万能只读 Token 无效"
_READONLY_WRITE_FORBIDDEN = "万能只读 Token 仅支持查询接口（GET/HEAD），不允许任何写操作"
_MIXED_READONLY = "请求不能同时携带万能只读 Token 与其他凭证"


@dataclass(frozen=True)
class CurrentUser:
    id: int
    display_name: str
    role: str
    auth_source: str  # unified | dev | service | readonly
    source_system: str = ""  # 仅 auth_source=service：服务 Token 绑定的来源系统


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


# ---------------------------------------------- 服务间机器凭证（系统侧）----

def _service_cache_ttl(expires_at_ms: object, now_seconds: float, default_ttl: float) -> float:
    """校验结果缓存 TTL：不得超过 Token 剩余有效期，且以常规 TTL 为较短
    上限（平台《服务Token接口对接文档》§4.2-3）。已过期返回 0（不缓存）。"""
    ttl = float(default_ttl)
    if isinstance(expires_at_ms, (int, float)) and expires_at_ms > 0:
        ttl = min(ttl, expires_at_ms / 1000.0 - now_seconds)
    return max(ttl, 0.0)


async def _service_gate(request: Request, token: str) -> None:
    """系统侧鉴权：校验 X-Service-Token 并检查来源系统接口白名单。
    平台校验不可达/不确定时拒绝（fail-closed），与用户侧同一原则。"""
    settings = get_settings()
    key = _cache_key(token, "X-SERVICE-TOKEN")
    user = _cache_get(key)
    if user is None:
        try:
            data = await run_in_threadpool(verify_service_token, token)
        except UnifiedAuthError as exc:
            raise BusinessError(str(exc) or _SERVICE_INVALID, status_code=401) from exc
        source = str(data.get("sourceSystem") or "").strip()
        # §4.2-4：仅 active=true 且 targetSystem 等于自身系统编码时接受身份
        if (
            not data.get("active")
            or str(data.get("targetSystem") or "") != settings.auth_system_code
            or not source
        ):
            raise BusinessError(_SERVICE_INVALID, status_code=401)
        user = CurrentUser(
            id=0,
            display_name=f"{source}-service",
            role="none",
            auth_source="service",
            source_system=source,
        )
        ttl = _service_cache_ttl(data.get("expiresAt"), time.time(), settings.auth_cache_ttl_seconds)
        if ttl > 0:
            _cache_put(key, user, ttl)
    _current_user.set(user)

    # §4.2-5/6：来源系统可访问面由本系统自管，凭证有效 ≠ 接口有权
    if not service_source_allowed(user.source_system, request.method, request.url.path):
        raise BusinessError(_SERVICE_FORBIDDEN, status_code=403)


# ---------------------------------------------- 万能只读 Token（自管凭证）----

# 万能只读身份：role=viewer 走既有角色梯度——全部查询面可读，/users 等
# sysadmin 面照旧拒绝；display_name 仅用于审计展示（GET-only，永不落库）
_READONLY_USER = CurrentUser(
    id=0, display_name="readonly-token", role="viewer", auth_source="readonly"
)


def _readonly_gate(method: str, path: str, token: str) -> None:
    """万能只读 Token 校验：本地常量时间比对，不经统一平台。

    只读约束是双保险：先硬性拒绝非 GET/HEAD（给出明确文案，而不是角色
    不足的笼统 403），再按 viewer 走 required_role 规则表兜底。"""
    settings = get_settings()
    configured = settings.readonly_token.strip()
    if not configured or not secrets.compare_digest(token.encode(), configured.encode()):
        raise BusinessError(_READONLY_INVALID, status_code=401)
    if method.upper() not in ("GET", "HEAD"):
        raise BusinessError(_READONLY_WRITE_FORBIDDEN, status_code=403)
    _current_user.set(_READONLY_USER)
    minimum = required_role(
        method, path, third_party_exempt=settings.third_party_exempt_enabled
    )
    if minimum is not None and not role_at_least(_READONLY_USER.role, minimum):
        raise BusinessError(_NO_PERMISSION, status_code=403)


# ------------------------------------------------------------ 全局依赖 ----

async def auth_gate(request: Request, db: Session = Depends(get_db)) -> None:
    settings = get_settings()

    if not settings.unified_auth_enabled:
        _current_user.set(_DEV_USER)
        return

    # §4.2-7：鉴权入口优先识别系统侧凭证，携带 X-Service-Token 的请求
    # 不得被用户 SSO 拦截层提前拒绝；§4.2-9：双 Token 同带拒绝，避免身份混用
    service_token = (request.headers.get("X-Service-Token") or "").strip()
    readonly_token = (request.headers.get("X-Readonly-Token") or "").strip()
    if readonly_token and (
        service_token or (request.headers.get("IDENTITYTOKEN") or "").strip()
    ):
        raise BusinessError(_MIXED_READONLY, status_code=400)
    if service_token:
        if (request.headers.get("IDENTITYTOKEN") or "").strip():
            raise BusinessError(_MIXED_TOKENS, status_code=400)
        await _service_gate(request, service_token)
        return
    if readonly_token:
        _readonly_gate(request.method, request.url.path, readonly_token)
        return

    minimum = required_role(
        request.method,
        request.url.path,
        third_party_exempt=settings.third_party_exempt_enabled,
    )
    if minimum is None:
        _current_user.set(None)
        return

    token = (request.headers.get("IDENTITYTOKEN") or "").strip()
    if not token:
        # 免鉴权关闭后，机器面路径上无凭证的调用方大概率是没升级的第三方——
        # 给出指向服务 Token 的明确文案，而不是误导性的"登录已过期"
        if not settings.third_party_exempt_enabled and any(
            p.match(request.url.path) for p in THIRD_PARTY_EXEMPT
        ):
            raise BusinessError(_SERVICE_REQUIRED, status_code=401)
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
