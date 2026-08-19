"""知识库分类树 + knowledge_base.category_id (PRD §4.11, issue #39)。

新表 knowledge_base_category（自引用树，parent_id=NULL 为顶级）；
knowledge_base 增加可空 category_id——存量知识库自然为 NULL(未分类)，
不需要数据回填。两个外键都是 RESTRICT：DB 层兜底「仅允许删除空分类」。

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_base_category",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, primary_key=True),
        sa.Column("parent_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
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
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["knowledge_base_category.id"],
            name="fk_category_parent",
            ondelete="RESTRICT",
        ),
        # MySQL 唯一索引不约束 NULL：顶级分类间的重名靠应用层查重，
        # 这个索引只兜底非顶级分类的并发重名写入（见 model 注释）
        sa.UniqueConstraint("parent_id", "name", name="uk_category_parent_name"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )

    op.add_column(
        "knowledge_base",
        sa.Column("category_id", mysql.BIGINT(unsigned=True), nullable=True),
    )
    op.create_index("ix_knowledge_base_category_id", "knowledge_base", ["category_id"])
    op.create_foreign_key(
        "fk_knowledge_base_category",
        "knowledge_base",
        "knowledge_base_category",
        ["category_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_knowledge_base_category", "knowledge_base", type_="foreignkey")
    op.drop_index("ix_knowledge_base_category_id", table_name="knowledge_base")
    op.drop_column("knowledge_base", "category_id")
    op.drop_table("knowledge_base_category")
