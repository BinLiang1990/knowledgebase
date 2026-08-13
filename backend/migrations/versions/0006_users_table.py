"""users 表：统一身份认证的用户身份快照 + 本系统授权。

issue #36：用户由统一平台下发（SSO 首登自动建快照），进门后的权限由
本系统用户管理页授权（design doc
docs/specs/2026-08-13-unified-identity-integration-design.md §3.1）。

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("identity_user_id", sa.BigInteger(), nullable=True),
        sa.Column("identity_account", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("auth_source", sa.String(16), nullable=False, server_default="unified"),
        sa.Column("org_id", sa.BigInteger(), nullable=True),
        sa.Column("org_code", sa.String(64), nullable=True),
        sa.Column("org_name", sa.String(255), nullable=True),
        sa.Column("platform_role_id", sa.BigInteger(), nullable=True),
        sa.Column("platform_role_code", sa.String(255), nullable=True),
        sa.Column("identity_updated_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("first_login_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="none"),
        sa.Column("role_granted_by", sa.String(100), nullable=True),
        sa.Column("role_granted_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
        ),
        sa.UniqueConstraint("identity_user_id", name="uk_users_identity_user_id"),
        mysql_charset="utf8mb4",
    )


def downgrade() -> None:
    op.drop_table("users")
