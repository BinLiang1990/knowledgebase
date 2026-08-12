"""答案关联三张表（docs/PRD-答案关联.md §6）。

关联端点 = (knowledge_point_id, coord_hash)，即一条版本链——不是某个具体
answer 行。刻意 **不建外键**：对端知识点被软删除、链被整链撤回时，关联记录
必须保留并在展示层灰态标记（PRD §3.6"历史永久可查"口径），外键约束反而会
阻碍这一点。answer_a_id/answer_b_id 只是"生成描述时采用的版本"快照，用于
审计，不用于 JOIN。
"""
from datetime import datetime

from sqlalchemy import CHAR, Enum, Float, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.mysql import BIGINT, JSON, LONGTEXT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_column, updated_at_column
from .knowledge_base import TABLE_ARGS


class AnswerRelation(Base):
    """两条版本链之间的一条无向关联。端点按 (kp_id, coord_hash) 排序规范化
    （a <= b），配合唯一约束保证同一对只有一条记录。"""

    __tablename__ = "answer_relation"
    __table_args__ = (
        UniqueConstraint(
            "kp_a_id", "coord_hash_a", "kp_b_id", "coord_hash_b", name="uq_answer_relation_pair"
        ),
        # 查询是"任一端属于该知识点"(OR 两个索引各自可用)，见 routers/relation.py
        Index("ix_answer_relation_kp_a", "kp_a_id"),
        Index("ix_answer_relation_kp_b", "kp_b_id"),
        TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    kb_a_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    kp_a_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    coord_hash_a: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    coord_a: Mapped[dict] = mapped_column(JSON, nullable=False)
    kb_b_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    kp_b_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    coord_hash_b: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    coord_b: Mapped[dict] = mapped_column(JSON, nullable=False)
    # 生成/添加时两端采用的当前生效版本与其内容哈希；stale 判定 = 任一端
    # content_hash 与该链当前生效版本不一致（查询时动态推导，不落库）
    answer_a_id: Mapped[int | None] = mapped_column(BIGINT(unsigned=True), nullable=True)
    answer_b_id: Mapped[int | None] = mapped_column(BIGINT(unsigned=True), nullable=True)
    content_hash_a: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    content_hash_b: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    # 手动添加且选择"AI 生成描述"时，描述在任务完成前为空字符串（生成中）
    description: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    # manual 的关联不会被后续 AI 分析覆盖（PRD §0.10）
    source: Mapped[str] = mapped_column(Enum("ai", "manual", name="answer_relation_source"), nullable=False)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operator: Mapped[str] = mapped_column(String(100), nullable=False, server_default="admin")
    created_at = created_at_column()
    updated_at = updated_at_column()


class AnswerEmbedding(Base):
    """每条版本链当前生效内容的向量缓存。content_hash/model 一起决定是否
    需要重算：内容变了、或换了向量模型，都会在下次分析时增量刷新。"""

    __tablename__ = "answer_embedding"
    __table_args__ = (
        UniqueConstraint("knowledge_point_id", "coord_hash", name="uq_answer_embedding_chain"),
        TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    knowledge_point_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    coord_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    vector: Mapped[list] = mapped_column(JSON, nullable=False)
    updated_at = updated_at_column()


class RelationTask(Base):
    """异步任务：analyze(以某知识点为中心的分析；center_coord_hash 为空 =
    知识点级自动关联，逐链执行) / generate_pair(为一条已存在的关联生成描述)。
    MySQL 即任务队列（PRD §0.8）：worker 以乐观 UPDATE 认领 pending 任务，
    进程启动时把遗留的 generating 重置回 pending。"""

    __tablename__ = "relation_task"
    __table_args__ = (
        Index("ix_relation_task_claim", "status", "updated_at"),
        Index("ix_relation_task_kp", "knowledge_point_id"),
        TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Enum("analyze", "generate_pair", name="relation_task_kind"), nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    knowledge_point_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    center_coord_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    pair_relation_id: Mapped[int | None] = mapped_column(BIGINT(unsigned=True), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("pending", "generating", "done", "failed", name="relation_task_status"),
        nullable=False,
        server_default="pending",
    )
    phase: Mapped[str | None] = mapped_column(String(20), nullable=True)
    progress_done: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    retry_count: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    operator: Mapped[str] = mapped_column(String(100), nullable=False, server_default="admin")
    created_at = created_at_column()
    updated_at = updated_at_column()
