"""knowledge_base 软删除 + 回收站（两级软删）。

- deleted_at / deleted_by：进入回收站的时间与操作人。deleted_at 非空 =
  已删除，除回收站接口外全部入口按"不存在"处理；
- purged_at：回收站内"彻底删除"的时间。同样是软删——数据永久保留在表里，
  仅从回收站列表消失、不可再还原。不加硬删路径，误操作永远可救。

status 枚举（active/deprecated）保持不动：删除是正交维度，仅 deprecated
状态的库允许进入回收站（应用层校验），还原后回到 deprecated。

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_base", sa.Column("deleted_at", mysql.DATETIME(fsp=6), nullable=True))
    op.add_column("knowledge_base", sa.Column("deleted_by", sa.String(100), nullable=True))
    op.add_column("knowledge_base", sa.Column("purged_at", mysql.DATETIME(fsp=6), nullable=True))


def downgrade() -> None:
    op.drop_column("knowledge_base", "purged_at")
    op.drop_column("knowledge_base", "deleted_by")
    op.drop_column("knowledge_base", "deleted_at")
