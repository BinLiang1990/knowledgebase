from datetime import date, datetime

from sqlalchemy import Boolean, CHAR, DateTime, ForeignKeyConstraint, Index, String, false
from sqlalchemy.dialects.mysql import BIGINT, JSON, LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_column
from .knowledge_base import TABLE_ARGS


class Answer(Base):
    __tablename__ = "answer"
    __table_args__ = (
        ForeignKeyConstraint(
            ["knowledge_point_id", "knowledge_base_id"],
            ["knowledge_point.id", "knowledge_point.knowledge_base_id"],
            ondelete="RESTRICT",
            name="fk_answer_kp_kb",
        ),
        Index("ix_answer_resolve", "knowledge_point_id", "coord_hash", "effective_time", "created_at"),
        TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    knowledge_point_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    coord: Mapped[dict] = mapped_column(JSON, nullable=False)
    coord_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    content: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    effective_time: Mapped[date] = mapped_column(nullable=False)
    operator: Mapped[str] = mapped_column(String(100), nullable=False, server_default="admin")
    source: Mapped[str] = mapped_column(String(100), nullable=False, server_default="人工填报")
    note: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at = created_at_column()
