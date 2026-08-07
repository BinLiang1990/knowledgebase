from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_column, updated_at_column
from .knowledge_base import TABLE_ARGS


class KnowledgePoint(Base):
    __tablename__ = "knowledge_point"
    __table_args__ = (
        UniqueConstraint("knowledge_base_id", "title", name="uq_kp_kb_title"),
        UniqueConstraint("id", "knowledge_base_id", name="uq_kp_id_kb"),
        TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("knowledge_base.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("active", "deleted", name="knowledge_point_status"), nullable=False, server_default="active"
    )
    operator: Mapped[str] = mapped_column(String(100), nullable=False, server_default="admin")
    created_at = created_at_column()
    updated_at = updated_at_column()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delete_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
