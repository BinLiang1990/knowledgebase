"""用户表（统一身份认证接入，issue #36）。

用户由统一身份平台下发：首次通过 SSO 进入时自动创建身份快照行，
不存密码。「平台快照字段」(identity_* / platform_* / org_*) 每次登录刷新；
「本系统授权字段」(role / role_granted_*) 只由用户管理页人工修改——
唯一例外是平台 roleCode=super_admin 自动成为 sysadmin
(docs/specs/2026-08-13-unified-identity-integration-design.md §D2)。
"""
from datetime import datetime

from sqlalchemy import BigInteger, String
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_column, updated_at_column


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ---- 平台身份快照（每次登录刷新，平台角色变化不影响本系统 role） ----
    identity_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    identity_account: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255), default="")
    auth_source: Mapped[str] = mapped_column(String(16), default="unified")  # unified | dev
    org_id: Mapped[int | None] = mapped_column(BigInteger)
    org_code: Mapped[str | None] = mapped_column(String(64))
    org_name: Mapped[str | None] = mapped_column(String(255))
    platform_role_id: Mapped[int | None] = mapped_column(BigInteger)
    platform_role_code: Mapped[str | None] = mapped_column(String(255))
    identity_updated_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    first_login_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))

    # ---- 本系统授权（人工授予；none=未授权，可登录但看不到业务数据） ----
    role: Mapped[str] = mapped_column(String(20), default="none")  # none|viewer|editor|admin|sysadmin
    role_granted_by: Mapped[str | None] = mapped_column(String(100))
    role_granted_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
