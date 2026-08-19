from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, created_at_column, updated_at_column
from .knowledge_base import TABLE_ARGS


class KnowledgeBaseCategory(Base):
    """知识库分类树 (PRD §4.11, issue #39)。

    parent_id=NULL 为顶级分类；「全部」「未分类」是前端的虚拟节点，不落库。
    同级排序由 sort_order 承载（数组下标语义，move 接口负责重排）。
    分类无留痕诉求（PRD §4.11），删除为物理删除。
    """

    __tablename__ = "knowledge_base_category"
    __table_args__ = (
        # MySQL 唯一索引不约束 NULL——顶级分类(parent_id IS NULL)之间的重名
        # 这个索引拦不住，路由层的应用级查重(_ensure_name_available)才是
        # 主防线；索引只兜底非顶级分类的并发重名写入。
        UniqueConstraint("parent_id", "name", name="uk_category_parent_name"),
        TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        # RESTRICT：有子分类的分类不允许删——与「仅允许删除空分类」的业务
        # 规则一致，DB 层兜底应用层校验
        ForeignKey("knowledge_base_category.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # PRD 上限 50 字（应用层校验）；列宽放到 100 给未来调整留余量
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at = created_at_column()
    updated_at = updated_at_column()
