"""认证接口的请求/响应模型（issue #36）。"""
from datetime import datetime

from pydantic import BaseModel, Field


class SsoLoginIn(BaseModel):
    ticket: str = Field(min_length=1, max_length=2000)
    # 当前统一平台通常只回传 ticket，缺省按同认证域处理（手册 §6.3）
    ticketType: str = Field(default="SAME_DOMAIN", max_length=20)


class CurrentUserOut(BaseModel):
    id: int
    display_name: str
    role: str
    auth_source: str


class UserOut(BaseModel):
    id: int
    identity_account: str | None
    display_name: str
    auth_source: str
    org_name: str | None
    platform_role_code: str | None
    role: str
    role_granted_by: str | None
    role_granted_at: datetime | None
    first_login_at: datetime | None


class UserRoleUpdate(BaseModel):
    role: str = Field(max_length=20)
