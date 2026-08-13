"""认证路由（issue #36，手册 §6.3）。

前端只与本后端交互：Ticket 换票、Token 校验、用户信息查询全部由这里
转发统一平台，浏览器绝不直连平台后端（手册 §10 红线）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..auth.sync import sync_identity
from ..auth.unified_client import (
    SystemAccessDenied,
    UnifiedAuthError,
    exchange_ticket,
    fetch_identity,
    fetch_role_codes,
)
from ..config import get_settings
from ..db import get_db
from ..envelope import BusinessError, envelope
from ..schemas.auth import CurrentUserOut, SsoLoginIn

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/sso_login")
def sso_login(payload: SsoLoginIn, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    if not settings.unified_auth_enabled:
        raise BusinessError("当前环境未启用统一身份认证登录", status_code=400)
    try:
        exchanged = exchange_ticket(payload.ticket, payload.ticketType)
        token_info = exchanged["tokenInfo"]
        token = token_info["tokenValue"]
        # 优先换票返回的设备类型；后续所有请求前端原样回传（手册 §3.3）
        app_type = token_info.get("loginDeviceType")
        identity = fetch_identity(token, app_type)
        role_codes = fetch_role_codes(token, app_type)
        user = sync_identity(db, {**exchanged["exchangeUser"], **identity}, role_codes)
    except SystemAccessDenied as exc:
        raise BusinessError(str(exc), status_code=403) from exc
    except UnifiedAuthError as exc:
        # Ticket 无效/已消费/平台失败 → 401；平台 msg 原样带回（手册 §9）
        raise BusinessError(str(exc), status_code=401) from exc
    return envelope(
        {
            "tokenInfo": {"tokenName": "IDENTITYTOKEN", **token_info},
            "user": CurrentUserOut(
                id=user.id,
                display_name=user.display_name,
                role=user.role,
                auth_source=user.auth_source,
            ).model_dump(mode="json"),
        }
    )


@router.get("/me")
def me() -> dict:
    user = get_current_user()
    if user is None:
        raise BusinessError("登录已过期，请重新登录", status_code=401)
    return envelope(
        CurrentUserOut(
            id=user.id, display_name=user.display_name, role=user.role, auth_source=user.auth_source
        ).model_dump(mode="json")
    )


@router.post("/logout")
def logout() -> dict:
    """本系统无服务端会话可清；统一 Token 的生命周期由平台管理，前端
    只需清掉本地存储。保留端点是为了前端有一个统一的退出调用点。"""
    return envelope()
