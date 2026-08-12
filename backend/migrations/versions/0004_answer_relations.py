"""答案关联三张表：answer_relation / answer_embedding / relation_task.

docs/PRD-答案关联.md §6。关联端点是版本链 (kp_id, coord_hash)，刻意不建
外键——对端软删除/整链撤回时关联保留、展示层灰态（PRD §3.6），外键会阻碍
这一语义。见 models/relation.py 的模块注释。

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

CHARSET_KW = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}


def created_at_col() -> sa.Column:
    return sa.Column(
        "created_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")
    )


def updated_at_col() -> sa.Column:
    return sa.Column(
        "updated_at",
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
    )


def upgrade() -> None:
    op.create_table(
        "answer_relation",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("kb_a_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("kp_a_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("coord_hash_a", sa.CHAR(64), nullable=False),
        sa.Column("coord_a", mysql.JSON(), nullable=False),
        sa.Column("kb_b_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("kp_b_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("coord_hash_b", sa.CHAR(64), nullable=False),
        sa.Column("coord_b", mysql.JSON(), nullable=False),
        sa.Column("answer_a_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("answer_b_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("content_hash_a", sa.CHAR(64), nullable=True),
        sa.Column("content_hash_b", sa.CHAR(64), nullable=True),
        sa.Column("description", mysql.LONGTEXT(), nullable=False),
        sa.Column("source", sa.Enum("ai", "manual", name="answer_relation_source"), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("operator", sa.String(100), nullable=False, server_default="admin"),
        created_at_col(),
        updated_at_col(),
        sa.UniqueConstraint(
            "kp_a_id", "coord_hash_a", "kp_b_id", "coord_hash_b", name="uq_answer_relation_pair"
        ),
        **CHARSET_KW,
    )
    op.create_index("ix_answer_relation_kp_a", "answer_relation", ["kp_a_id"])
    op.create_index("ix_answer_relation_kp_b", "answer_relation", ["kp_b_id"])

    op.create_table(
        "answer_embedding",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("knowledge_base_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("knowledge_point_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("coord_hash", sa.CHAR(64), nullable=False),
        sa.Column("content_hash", sa.CHAR(64), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("vector", mysql.JSON(), nullable=False),
        updated_at_col(),
        sa.UniqueConstraint("knowledge_point_id", "coord_hash", name="uq_answer_embedding_chain"),
        **CHARSET_KW,
    )

    op.create_table(
        "relation_task",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.Enum("analyze", "generate_pair", name="relation_task_kind"), nullable=False),
        sa.Column("knowledge_base_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("knowledge_point_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("center_coord_hash", sa.CHAR(64), nullable=True),
        sa.Column("pair_relation_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "generating", "done", "failed", name="relation_task_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("phase", sa.String(20), nullable=True),
        sa.Column("progress_done", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("retry_count", mysql.TINYINT(unsigned=True), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("operator", sa.String(100), nullable=False, server_default="admin"),
        created_at_col(),
        updated_at_col(),
        **CHARSET_KW,
    )
    op.create_index("ix_relation_task_claim", "relation_task", ["status", "updated_at"])
    op.create_index("ix_relation_task_kp", "relation_task", ["knowledge_point_id"])


def downgrade() -> None:
    op.drop_table("relation_task")
    op.drop_table("answer_embedding")
    op.drop_table("answer_relation")
