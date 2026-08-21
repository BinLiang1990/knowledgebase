from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _stripped_non_empty(v: str, field_label: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError(f"{field_label}不能为空")
    return v


# 数据来源（产生方式）：调用方可自报的两种。第三种"批量导入"由
# batch-import 端点服务端固定写入，不接受自报。
AnswerSourceInput = Literal["人工填报", "AI生成"]


class DefaultAnswerInput(BaseModel):
    content: str = Field(min_length=1)
    effective_time: date
    note: str | None = None
    source: AnswerSourceInput = "人工填报"


class KnowledgePointCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    default_answer: DefaultAnswerInput | None = None

    @field_validator("title")
    @classmethod
    def _validate_title(cls, v: str) -> str:
        return _stripped_non_empty(v, "标题")


class KnowledgePointBatchImportRequest(BaseModel):
    # max_length=500: bounds request processing time/transaction length for
    # this endpoint's per-item SAVEPOINT loop — does not bound total request
    # body size (content/note have no length cap per PRD §4.5, a known,
    # accepted residual risk carried over unchanged from the single-item
    # endpoint). Design doc §2 (issue #11).
    items: list[KnowledgePointCreate] = Field(min_length=1, max_length=500)


class BatchImportItemResult(BaseModel):
    index: int
    status: Literal["created", "failed"]
    title: str
    knowledge_point_id: int | None = None
    reason: str | None = None


class BatchImportResult(BaseModel):
    created_count: int
    failed_count: int
    results: list[BatchImportItemResult]


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
    source: AnswerSourceInput = "人工填报"
    # issue #32：目标条件组合当前是撤回态时必填（接口层校验，见
    # _reactivate_chain_if_revoked）；其余情况可不传/被忽略
    reactivate_reason: str | None = Field(default=None, max_length=500)


class AnswerEdit(BaseModel):
    content: str = Field(min_length=1)
    effective_time: date
    note: str | None = None
    # None is the "field omitted" sentinel (keep the existing coord
    # unchanged) — see the validator below for why an explicit JSON `null`
    # is rejected rather than silently treated the same way.
    coord: dict[str, Any] | None = None
    # None = 继承被编辑答案的 source（含"批量导入"）；显式传值可改写——
    # 例如把 AI 生成的内容人工核对后自报"人工填报"
    source: AnswerSourceInput | None = None
    migration_reason: str | None = Field(default=None, max_length=500)
    # issue #32：编辑落点的链（迁移后的新条件，或原条件本身）处于撤回态时必填
    reactivate_reason: str | None = Field(default=None, max_length=500)

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
    source_system: str
    note: str | None
    revoked: bool
    revoked_at: datetime | None
    revoked_by: str | None
    revoke_reason: str | None
    # issue #32：最近一次恢复的信息；恢复时 revoked_* 保留原样当历史
    reactivated_at: datetime | None
    reactivated_by: str | None
    reactivate_reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnswerPromoteToDefault(BaseModel):
    effective_time: date
    note: str | None = None
    # issue #32：默认答案链处于撤回态时必填
    reactivate_reason: str | None = Field(default=None, max_length=500)


class AnswerRevoke(BaseModel):
    # max_length=500: Answer.revoke_reason is a String(500) column, not
    # LONGTEXT like content/note — matches KnowledgePointDeleteRequest
    # .delete_reason and AnswerEdit.migration_reason's own cap on the same
    # kind of field. Design doc §2 (issue #10).
    revoke_reason: str = Field(min_length=1, max_length=500)

    @field_validator("revoke_reason")
    @classmethod
    def _validate_reason(cls, v: str) -> str:
        return _stripped_non_empty(v, "撤回原因")


class ResolvedOut(BaseModel):
    status: Literal["exact", "weighted", "default", "fallback-latest", "none"]
    answer: AnswerOut | None


class AnswerGroupOut(BaseModel):
    coord: dict[str, Any]
    revoked: bool
    version_count: int
    latest_answer: AnswerOut
    live_answer: AnswerOut | None
