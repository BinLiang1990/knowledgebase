"""统一身份认证平台客户端（手册 §3/§6.1，issue #36）。

纯逻辑（签名/包络解析/设备类型归一）与 HTTP 调用分开：前者可被
不依赖网络与数据库的单测覆盖（backend/tests/test_unified_auth_logic.py）。

安全红线（手册 §10）：clientSecret 只从配置读取，不出现在日志/异常文本；
Ticket/Token 同样不落日志。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Any

import httpx

from ..config import get_settings

logger = logging.getLogger("kb_backend")

APP_TYPES = {"PORTAL", "ADMIN", "H5", "DASHBOARD"}
TICKET_TYPES = {"SAME_DOMAIN", "CROSS_DOMAIN"}
EXCHANGE_PATH = "/core/sso/exchange"
CROSS_DOMAIN_PATH = "/core/cross-domain/session/login"
USERINFO_PATH = "/core/user/userInfo"
ROLE_LIST_PATH = "/core/user/roleList"


class UnifiedAuthError(Exception):
    """统一平台调用失败 / 响应不合契约 / 业务失败（保留平台 msg）。"""


class SystemAccessDenied(Exception):
    """认证成功但用户无本系统访问资格（→ HTTP 403）。"""


# ---------------------------------------------------------------- 纯逻辑 ----

def compact_json_bytes(data: dict[str, Any]) -> bytes:
    """紧凑 JSON（无空格、UTF-8、中文不转义）——参与 HMAC 摘要的字节必须
    与实际发送的字节完全一致（手册 §3.1），所以序列化只做这一次，
    发送时直接用这份字节。"""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def hmac_signature(
    secret: str, path: str, client_id: str, timestamp: str, nonce: str, body_bytes: bytes
) -> str:
    """六段式签名原文：POST/路径/clientId/时间戳/nonce/SHA256(请求体)，
    换行连接、末尾不追加换行（手册 §3.1）。"""
    digest = hashlib.sha256(body_bytes).hexdigest()
    message = f"POST\n{path}\n{client_id}\n{timestamp}\n{nonce}\n{digest}"
    return hmac.new(secret.encode(), message.encode("utf-8"), hashlib.sha256).hexdigest()


def unwrap(body: Any) -> dict[str, Any]:
    """平台业务包络解析：只有业务 code=200 才是成功（HTTP 200 也可能是业务
    失败，手册 §3.1），失败时必须保留平台 msg 原文。"""
    if not isinstance(body, dict):
        raise UnifiedAuthError("统一身份认证平台返回格式无效")
    if body.get("code") is None:
        return body
    if str(body.get("code")) != "200":
        raise UnifiedAuthError(str(body.get("msg") or body.get("message") or "统一身份认证平台处理失败"))
    data = body.get("data")
    return data if isinstance(data, dict) else {}


def normalize_app_type(value: str | None, fallback: str = "ADMIN") -> str:
    """设备类型归一：优先换票返回的 loginDeviceType，非法值回落配置兜底
    （手册 §3.3——不能把任意前端传值原样转发给平台）。"""
    fb = fallback.strip().upper()
    if fb not in APP_TYPES:
        fb = "ADMIN"
    current = str(value or "").strip().upper()
    return current if current in APP_TYPES else fb


# ---------------------------------------------------------------- HTTP ----

def _hmac_headers(path: str, body_bytes: bytes) -> dict[str, str]:
    settings = get_settings()
    if not settings.identity_client_secret:
        raise UnifiedAuthError("服务端未配置统一身份认证密钥")
    timestamp = str(int(time.time() * 1000))
    nonce = secrets.token_hex(16)
    signature = hmac_signature(
        settings.identity_client_secret,
        path,
        settings.identity_client_id_effective,
        timestamp,
        nonce,
        body_bytes,
    )
    return {
        "Content-Type": "application/json",
        "X-Sso-Client": settings.identity_client_id_effective,
        "system-code": settings.auth_system_code,
        "X-Sso-Timestamp": timestamp,
        "X-Sso-Nonce": nonce,
        "X-Sso-Signature": signature,
    }


def _post(url: str, *, content: bytes | None = None, json_body: dict | None = None, headers: dict[str, str]) -> Any:
    settings = get_settings()
    try:
        resp = httpx.post(
            url,
            content=content,
            json=json_body,
            headers=headers,
            timeout=settings.identity_sso_timeout,
        )
    except httpx.HTTPError as exc:
        # 不带 URL 细节往外抛，避免日志里出现带 Ticket 的完整 URL
        logger.warning("统一平台请求失败: %s %s", url.split("?")[0], type(exc).__name__)
        raise UnifiedAuthError("统一身份认证平台暂时不可用") from exc
    try:
        body = resp.json()
    except ValueError as exc:
        logger.warning("统一平台响应非 JSON: %s http=%s", url.split("?")[0], resp.status_code)
        raise UnifiedAuthError("统一身份认证平台返回格式无效") from exc
    if resp.status_code >= 400:
        message = body.get("msg") if isinstance(body, dict) else None
        raise UnifiedAuthError(str(message or "统一身份认证平台请求失败"))
    return body


def exchange_ticket(ticket: str, ticket_type: str = "SAME_DOMAIN") -> dict[str, Any]:
    """Ticket 换统一 Token。返回 {"tokenInfo": {...}, "exchangeUser": {...}}。"""
    settings = get_settings()
    ticket = (ticket or "").strip()
    ticket_type = (ticket_type or "SAME_DOMAIN").strip().upper()
    if not ticket:
        raise UnifiedAuthError("单点登录票据不能为空")
    if ticket_type not in TICKET_TYPES:
        raise UnifiedAuthError("不支持的单点登录票据类型")
    if ticket_type not in settings.accepted_ticket_types:
        raise UnifiedAuthError("当前系统不接受此类型的单点登录票据")

    path = EXCHANGE_PATH if ticket_type == "SAME_DOMAIN" else CROSS_DOMAIN_PATH
    request_data: dict[str, Any] = {"ticket": ticket}
    if ticket_type == "CROSS_DOMAIN":
        # systemCode 由后端固定配置，绝不接受前端指定（手册 §3.2）
        request_data.update({"ticketType": ticket_type, "systemCode": settings.auth_system_code})
    body_bytes = compact_json_bytes(request_data)
    url = settings.identity_base_url.rstrip("/") + path
    body = _post(url, content=body_bytes, headers=_hmac_headers(path, body_bytes))
    data = unwrap(body)
    if data.get("systemCode") and data["systemCode"] != settings.auth_system_code:
        raise UnifiedAuthError("Ticket 目标系统不匹配")
    token_info = data.get("tokenInfo") or {}
    if not token_info.get("tokenValue"):
        raise UnifiedAuthError("统一身份认证平台未返回统一 Token")
    return {"tokenInfo": token_info, "exchangeUser": data}


def _identity_headers(token: str, app_type: str | None) -> dict[str, str]:
    settings = get_settings()
    return {
        "IDENTITYTOKEN": token,
        "X-App-Type": normalize_app_type(app_type, settings.identity_app_type),
        "system-code": settings.auth_system_code,
    }


def fetch_identity(token: str, app_type: str | None) -> dict[str, Any]:
    """查询当前统一用户；校验本系统访问资格（systems 名单）。"""
    settings = get_settings()
    url = settings.identity_base_url.rstrip("/") + USERINFO_PATH
    body = _post(url, json_body={}, headers=_identity_headers(token, app_type))
    data = unwrap(body)
    identity = data.get("user") or data.get("identityUser") or data
    if not isinstance(identity, dict) or not (identity.get("id") or identity.get("userId")):
        raise UnifiedAuthError("统一身份认证平台未返回用户ID")
    systems = identity.get("systems")
    if isinstance(systems, list) and settings.auth_system_code not in systems:
        raise SystemAccessDenied("当前用户无本系统访问权限")
    return identity


def fetch_role_codes(token: str, app_type: str | None) -> set[str]:
    """查询当前用户的平台角色编码集合（小写）。"""
    settings = get_settings()
    url = settings.identity_base_url.rstrip("/") + ROLE_LIST_PATH
    body = _post(url, json_body={}, headers=_identity_headers(token, app_type))
    if not isinstance(body, dict):
        raise UnifiedAuthError("统一身份认证平台角色返回格式无效")
    if body.get("code") is not None and str(body.get("code")) != "200":
        raise UnifiedAuthError(str(body.get("msg") or "统一身份认证平台角色查询失败"))
    items = body.get("data") or []
    if not isinstance(items, list):
        raise UnifiedAuthError("统一身份认证平台角色返回格式无效")
    return {
        str(item.get("roleCode") or "").strip().lower()
        for item in items
        if isinstance(item, dict) and item.get("roleCode")
    }
