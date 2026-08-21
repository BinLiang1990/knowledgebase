from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.mysql import BIGINT, DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_column, updated_at_column

TABLE_ARGS = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 所属分类 (PRD §4.11, issue #39)：NULL = 未分类。RESTRICT——有知识库
    # （含已停用的）归属的分类不允许删，DB 层兜底「仅允许删除空分类」规则
    category_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("knowledge_base_category.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        Enum("active", "deprecated", name="knowledge_base_status"),
        nullable=False,
        server_default="active",
    )
    # 两级软删（migration 0009）：deleted_at 非空 = 在回收站（仅 deprecated
    # 可删，还原后回到 deprecated）；purged_at 非空 = 回收站内"彻底删除"——
    # 同样是软删，数据保留，仅从回收站消失、不可再还原。status 不感知删除。
    deleted_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    deleted_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    created_at = created_at_column()
    updated_at = updated_at_column()
