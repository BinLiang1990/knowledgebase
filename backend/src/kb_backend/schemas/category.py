from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# PRD §4.11：名称去首尾空格后非空、≤50 字。Field 的 max_length 在 strip 之前
# 生效，所以精确的 50 字校验放在 validator 里（strip 之后）；Field 上限只做
# 粗兜底，防止超长输入进入 validator。
_NAME_RAW_MAX = 200


def _stripped_category_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("分类名称不能为空")
    if len(v) > 50:
        raise ValueError("分类名称不能超过 50 字")
    return v


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=_NAME_RAW_MAX)
    parent_id: int | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _stripped_category_name(v)


class CategoryUpdate(BaseModel):
    # parent_id 需区分「未传(不改)」与「显式 null(移到顶级)」——路由层用
    # model_fields_set 判断，与 KnowledgeBaseUpdate.description 的处理一致
    name: str | None = Field(default=None, min_length=1, max_length=_NAME_RAW_MAX)
    parent_id: int | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _stripped_category_name(v)


class CategoryMove(BaseModel):
    """拖拽落点 (PRD §4.11)：before/after = 插入为目标的前/后同级（父级取
    目标的父级），inside = 挂为目标的子分类、排子级末尾。"""

    target_id: int
    position: Literal["before", "after", "inside"]


class CategoryOut(BaseModel):
    id: int
    parent_id: int | None
    name: str
    sort_order: int
    # 直属的启用中知识库数（PRD §4.11 未决 #1 的建议口径：不含已停用）；
    # 子树合计由前端聚合，避免后端重复算整棵树
    active_knowledge_base_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
