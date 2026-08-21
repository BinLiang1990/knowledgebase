from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


def _stripped_non_empty_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("名称不能为空")
    return v


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    # 创建时直接启用维度（可选）——省去"建库后必须再去知识库设置勾选"的
    # 二段式操作。省略/None/[] 都等价于旧行为：不启用任何维度。
    # 长度上限镜像 EnabledDimensionsUpdate.dimension_keys 的理由
    # （schemas/dimension.py）。
    enabled_dimension_keys: list[Annotated[str, Field(max_length=100)]] | None = Field(
        default=None, max_length=200
    )
    # 所属分类 (PRD §4.11, issue #39)：省略/None = 未分类
    category_id: int | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _stripped_non_empty_name(v)


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    # 同 description：区分「未传(不改)」与「显式 null(置为未分类)」，
    # 路由层用 model_fields_set 判断
    category_id: int | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _stripped_non_empty_name(v)


class KnowledgeBaseOut(BaseModel):
    id: int
    name: str
    description: str | None
    status: Literal["active", "deprecated"]
    active_knowledge_point_count: int
    # 所属分类 (PRD §4.11)：对外列表接口也返回，第三方可据此自行判断
    # "未分类"(两者皆 null)；名称随 id 一并给出，免得对接方再拉分类树
    category_id: int | None = None
    category_name: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeBaseRecycleOut(KnowledgeBaseOut):
    """回收站条目：在 KnowledgeBaseOut 之上补删除留痕。status 恒为
    deprecated（仅停用库可删，还原后也回到停用）。"""

    deleted_at: datetime
    deleted_by: str | None


class KnowledgeBaseStatsOut(BaseModel):
    subject_count: int
    active_answer_count: int
    enabled_dimension_count: int
    today_change_count: int
