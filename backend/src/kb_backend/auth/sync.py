"""统一用户身份快照同步（手册 §5/§6.2，issue #36）。

规则（设计文档 §D2）：
- 按统一 userId 首登即建快照行，不预建账号、不存平台密码；
- 快照字段每次登录刷新；本系统 role 是人工授权，平台角色变化不覆盖——
  唯一例外：roleCode=super_admin 自动确保 sysadmin；
- 平台侧降级(super_admin 被摘)不自动撤销本系统 sysadmin，撤权走用户
  管理页人工操作（手册 §5.6 留给项目决定，这里选择保守不自动撤权）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.user import User
from .roles import is_platform_super_admin
from .unified_client import UnifiedAuthError


def sync_identity(db: Session, identity: dict[str, Any], role_codes: set[str]) -> User:
    """登录/校验时同步身份快照，返回本地用户行（已 commit）。"""
    raw_id = identity.get("userId") or identity.get("id")
    if raw_id in (None, ""):
        raise UnifiedAuthError("统一身份认证平台未返回用户ID")
    identity_user_id = int(raw_id)

    user = db.execute(
        select(User).where(User.identity_user_id == identity_user_id)
    ).scalar_one_or_none()

    now = datetime.now()
    account = str(identity.get("account") or f"identity:{identity_user_id}")
    display_name = str(identity.get("realName") or identity.get("account") or account)

    if user is None:
        user = User(
            identity_user_id=identity_user_id,
            auth_source="unified",
            role="none",
            first_login_at=now,
        )
        db.add(user)

    # ---- 快照字段：每次刷新 ----
    user.identity_account = account
    user.display_name = display_name
    org_id = identity.get("orgId")
    user.org_id = int(org_id) if org_id not in (None, "") else None
    user.org_code = str(identity.get("orgCode")) if identity.get("orgCode") else None
    user.org_name = str(identity.get("orgName")) if identity.get("orgName") else None
    role_id = identity.get("roleId")
    user.platform_role_id = int(role_id) if role_id not in (None, "") else None
    user.platform_role_code = ",".join(sorted(role_codes)) if role_codes else None
    user.identity_updated_at = now

    # ---- 授权字段：只有 super_admin 自动提权，其余一律不动 ----
    if is_platform_super_admin(role_codes) and user.role != "sysadmin":
        user.role = "sysadmin"
        user.role_granted_by = "统一平台 super_admin 自动授予"
        user.role_granted_at = now

    db.commit()
    db.refresh(user)
    return user
