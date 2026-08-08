from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _stripped_non_empty(v: str, field_label: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError(f"{field_label}不能为空")
    return v


class DefaultAnswerInput(BaseModel):
    content: str = Field(min_length=1)
    effective_time: date
    note: str | None = None


class KnowledgePointCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    default_answer: DefaultAnswerInput | None = None

    @field_validator("title")
    @classmethod
    def _validate_title(cls, v: str) -> str:
        return _stripped_non_empty(v, "标题")


class KnowledgePointUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, v: str) -> str:
        return _stripped_non_empty(v, "标题")


class KnowledgePointDeleteRequest(BaseModel):
    delete_reason: str = Field(min_length=1, max_length=500)

    @field_validator("delete_reason")
    @classmethod
    def _validate_reason(cls, v: str) -> str:
        return _stripped_non_empty(v, "删除原因")


class KnowledgePointOut(BaseModel):
    id: int
    knowledge_base_id: int
    title: str
    status: Literal["active", "deleted"]
    operator: str
    active_answer_count: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    delete_reason: str | None

    model_config = {"from_attributes": True}


class AnswerCreate(BaseModel):
    content: str = Field(min_length=1)
    effective_time: date
    coord: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class AnswerEdit(BaseModel):
    content: str = Field(min_length=1)
    effective_time: date
    note: str | None = None
    # None is the "field omitted" sentinel (keep the existing coord
    # unchanged) — see the validator below for why an explicit JSON `null`
    # is rejected rather than silently treated the same way.
    coord: dict[str, Any] | None = None
    migration_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_null_coord(cls, data: Any) -> Any:
        # "coord omitted" (keep unchanged) and "coord explicitly {}" (target
        # the default-answer group) are both meaningful and distinct; a
        # literal JSON null for coord is neither, so reject it outright
        # instead of silently aliasing it to one of the two.
        if isinstance(data, dict) and data.get("coord", "___absent___") is None:
            raise ValueError("coord 不能为 null；不携带该字段表示条件不变，传 {} 表示改为默认条件")
        return data


class AnswerOut(BaseModel):
    id: int
    knowledge_base_id: int
    knowledge_point_id: int
    coord: dict[str, Any]
    coord_hash: str
    content: str
    effective_time: date
    operator: str
    source: str
    note: str | None
    revoked: bool
    revoked_at: datetime | None
    revoked_by: str | None
    revoke_reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ResolvedOut(BaseModel):
    status: Literal["exact", "weighted", "default", "fallback-latest", "none"]
    answer: AnswerOut | None


class AnswerGroupOut(BaseModel):
    coord: dict[str, Any]
    revoked: bool
    version_count: int
    latest_answer: AnswerOut
    live_answer: AnswerOut | None
