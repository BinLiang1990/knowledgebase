"""answer 表新增重新启用三件套：reactivated_at / reactivated_by / reactivate_reason.

issue #32：撤回后的条件组合通过"新增答案"路径重新启用，恢复时 revoked_*
保留原样当历史，本组字段记录最近一次恢复（设计文档
docs/specs/2026-08-12-answer-reactivate-design.md §1）。

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("answer", sa.Column("reactivated_at", sa.DateTime(), nullable=True))
    op.add_column("answer", sa.Column("reactivated_by", sa.String(100), nullable=True))
    op.add_column("answer", sa.Column("reactivate_reason", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("answer", "reactivate_reason")
    op.drop_column("answer", "reactivated_by")
    op.drop_column("answer", "reactivated_at")
