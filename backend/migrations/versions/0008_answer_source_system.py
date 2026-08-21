"""answer 表新增 source_system（操作系统）+ source 值归一。

变更留痕三元组（操作人 / 操作系统 / 数据来源）的存储侧：

- 新增 source_system 列：写入方系统编码，服务凭证写入 = 平台来源系统
  编码（bqxt/yhfkglxt…），运营端写入 = tyzsk。存量数据回填 tyzsk——
  历史写入全部来自本系统运营端（服务 Token 写面 2026-08-21 才开放）；
- source 列收敛为三值枚举：人工填报 / AI生成 / 批量导入。存量的
  "人工编辑"归一为"人工填报"——"这次是编辑"属于动作信息，change_log
  的时间线本就记录（action=edit），source 只表达产生方式。

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "answer",
        sa.Column("source_system", sa.String(100), nullable=False, server_default="tyzsk"),
    )
    op.execute("UPDATE answer SET source = '人工填报' WHERE source = '人工编辑'")


def downgrade() -> None:
    # source 值归一不可逆（哪些行原本是"人工编辑"已不可知）；动作信息
    # 仍可从 change_log 推导（action=edit），故降级仅还原表结构。
    op.drop_column("answer", "source_system")
