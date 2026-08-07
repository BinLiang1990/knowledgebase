"""Initial schema: knowledge_base, dimension_definition,
knowledge_base_enabled_dimension, knowledge_point, answer.

Revision ID: 0001
Revises:
Create Date: 2026-08-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

CHARSET_KW = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}


def upgrade() -> None:
    op.create_table(
        "knowledge_base",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "deprecated", name="knowledge_base_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("name", name="uq_knowledge_base_name"),
        **CHARSET_KW,
    )

    op.create_table(
        "dimension_definition",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column(
            "field_type",
            sa.Enum("text", "number", "date", "boolean", name="dimension_field_type"),
            nullable=False,
        ),
        sa.Column(
            "weight", mysql.SMALLINT(unsigned=True), nullable=False, server_default="50"
        ),
        sa.Column("default_value", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "deprecated", name="dimension_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
        sa.CheckConstraint("weight BETWEEN 1 AND 100", name="ck_dimension_weight"),
        **CHARSET_KW,
    )

    op.create_table(
        "knowledge_base_enabled_dimension",
        sa.Column("knowledge_base_id", mysql.BIGINT(unsigned=True), primary_key=True),
        sa.Column("dimension_key", sa.String(100), primary_key=True),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["knowledge_base.id"], ondelete="RESTRICT", name="fk_kbed_kb"
        ),
        sa.ForeignKeyConstraint(
            ["dimension_key"], ["dimension_definition.key"], ondelete="RESTRICT", name="fk_kbed_dim"
        ),
        **CHARSET_KW,
    )

    op.create_table(
        "knowledge_point",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("knowledge_base_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "deleted", name="knowledge_point_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("operator", sa.String(100), nullable=False, server_default="admin"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("delete_reason", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["knowledge_base.id"], ondelete="RESTRICT", name="fk_kp_kb"
        ),
        sa.UniqueConstraint("knowledge_base_id", "title", name="uq_kp_kb_title"),
        sa.UniqueConstraint("id", "knowledge_base_id", name="uq_kp_id_kb"),
        **CHARSET_KW,
    )

    op.create_table(
        "answer",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("knowledge_base_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("knowledge_point_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("coord", mysql.JSON(), nullable=False),
        sa.Column("coord_hash", sa.CHAR(64), nullable=False),
        sa.Column("content", mysql.LONGTEXT(), nullable=False),
        sa.Column("effective_time", sa.Date(), nullable=False),
        sa.Column("operator", sa.String(100), nullable=False, server_default="admin"),
        sa.Column("source", sa.String(100), nullable=False, server_default="人工填报"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_by", sa.String(100), nullable=True),
        sa.Column("revoke_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id", "knowledge_base_id"],
            ["knowledge_point.id", "knowledge_point.knowledge_base_id"],
            ondelete="RESTRICT",
            name="fk_answer_kp_kb",
        ),
        **CHARSET_KW,
    )
    op.create_index(
        "ix_answer_resolve",
        "answer",
        ["knowledge_point_id", "coord_hash", "effective_time", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("answer")
    op.drop_table("knowledge_point")
    op.drop_table("knowledge_base_enabled_dimension")
    op.drop_table("dimension_definition")
    op.drop_table("knowledge_base")
