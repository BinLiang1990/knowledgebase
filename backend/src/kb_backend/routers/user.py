"""用户管理路由（issue #36，仅 sysadmin——roles.required_role 规则表拦截）。

打标系统同款模式：统一用户首次进入后自动出现在这里；未授权(role=none)
时可登录但看不到业务数据，由系统管理员在本页授予角色。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import current_operator, get_current_user, invalidate_token_cache
from ..auth.roles import ASSIGNABLE_ROLES
from ..db import get_db
from ..envelope import BusinessError, envelope
from ..models.user import User
from ..schemas.auth import UserOut, UserRoleUpdate

router = APIRouter(prefix="/users", tags=["user"])

_NOT_FOUND_MSG = "用户不存在"


def _to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        identity_account=user.identity_account,
        display_name=user.display_name,
        auth_source=user.auth_source,
        org_name=user.org_name,
        platform_role_code=user.platform_role_code,
        role=user.role,
        role_granted_by=user.role_granted_by,
        role_granted_at=user.role_granted_at,
        first_login_at=user.first_login_at,
    )


@router.get("")
def list_users(db: Session = Depends(get_db)) -> dict:
    users = db.execute(select(User).order_by(User.first_login_at.desc(), User.id.desc())).scalars().all()
    return envelope({"items": [_to_out(u).model_dump(mode="json") for u in users]})


@router.patch("/{user_id}/role")
def update_user_role(user_id: int, payload: UserRoleUpdate, db: Session = Depends(get_db)) -> dict:
    role = payload.role.strip().lower()
    if role not in ASSIGNABLE_ROLES:
        raise BusinessError("无效的角色", status_code=400)

    user = db.get(User, user_id)
    if user is None:
        raise BusinessError(_NOT_FOUND_MSG, status_code=404)

    me = get_current_user()
    if me is not None and me.auth_source == "unified" and me.id == user.id:
        # 防呆：sysadmin 把自己降级会当场失去用户管理入口，要求换个管理员操作
        raise BusinessError("不能修改自己的角色", status_code=400)

    user.role = role
    user.role_granted_by = current_operator()
    user.role_granted_at = datetime.now()
    db.commit()
    db.refresh(user)

    # 让被改用户已缓存的 Token 校验结果立刻失效，新角色即时生效
    invalidate_token_cache()
    return envelope(_to_out(user).model_dump(mode="json"))
