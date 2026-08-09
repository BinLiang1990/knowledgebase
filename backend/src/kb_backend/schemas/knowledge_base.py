from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _stripped_non_empty_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("名称不能为空")
    return v


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _stripped_non_empty_name(v)


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)

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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeBaseStatsOut(BaseModel):
    subject_count: int
    active_answer_count: int
    enabled_dimension_count: int
    today_change_count: int
