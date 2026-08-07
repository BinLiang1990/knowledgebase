from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.mysql import BIGINT, SMALLINT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .knowledge_base import TABLE_ARGS


class DimensionDefinition(Base):
    __tablename__ = "dimension_definition"
    __table_args__ = (
        CheckConstraint("weight BETWEEN 1 AND 100", name="ck_dimension_weight"),
        TABLE_ARGS,
    )

    key: Mapped[str] = mapped_column("key", String(100), primary_key=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    field_type: Mapped[str] = mapped_column(
        Enum("text", "number", "date", "boolean", name="dimension_field_type"), nullable=False
    )
    weight: Mapped[int] = mapped_column(SMALLINT(unsigned=True), nullable=False, server_default="50")
    default_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("active", "deprecated", name="dimension_status"), nullable=False, server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class KnowledgeBaseEnabledDimension(Base):
    __tablename__ = "knowledge_base_enabled_dimension"
    __table_args__ = TABLE_ARGS

    knowledge_base_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("knowledge_base.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    dimension_key: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("dimension_definition.key", ondelete="RESTRICT"),
        primary_key=True,
    )
