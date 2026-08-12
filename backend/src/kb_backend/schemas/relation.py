"""答案关联的请求/响应模型（docs/PRD-答案关联.md §3.4）。"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    # 为空 = 知识点级自动关联(全部有效链逐条召回)，见 PRD §3.1
    coord_hash: str | None = Field(default=None, min_length=64, max_length=64)


class EndpointRef(BaseModel):
    kb_id: int
    kp_id: int
    coord_hash: str = Field(min_length=64, max_length=64)


class RelationCreate(BaseModel):
    a: EndpointRef
    b: EndpointRef
    description: str | None = None
    # description 为空且 generate=true：先落一条空描述的关联，再登记单对
    # 生成任务，前端按"生成中"展示
    generate: bool = False


class RelationUpdate(BaseModel):
    description: str = Field(min_length=1)


class RelationEndpointOut(BaseModel):
    kb_id: int
    kp_id: int
    coord_hash: str
    coord: dict[str, Any]
    kb_name: str | None
    kp_title: str | None
    # ok=正常 / revoked=链无生效版本 / kp-deleted=知识点已软删除 / missing=数据缺失
    state: Literal["ok", "revoked", "kp-deleted", "missing"]
    current_content_preview: str | None


class RelationOut(BaseModel):
    id: int
    a: RelationEndpointOut
    b: RelationEndpointOut
    description: str
    source: Literal["ai", "manual"]
    similarity: float | None
    model: str | None
    operator: str
    # stale：任一端当前生效内容与生成时的内容哈希不一致（动态推导）
    stale: bool
    # generating：手动添加时选择 AI 生成、描述尚未产出
    generating: bool
    created_at: datetime
    updated_at: datetime


class RelationsOut(BaseModel):
    # disabled=未配置网关 / generating=有任务执行中 / pending=有任务排队 / idle
    generation_status: Literal["disabled", "generating", "pending", "idle"]
    relations: list[RelationOut]


class TaskOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    kind: Literal["analyze", "generate_pair"]
    knowledge_base_id: int
    knowledge_point_id: int
    center_coord_hash: str | None
    pair_relation_id: int | None
    status: Literal["pending", "generating", "done", "failed"]
    phase: str | None
    progress_done: int
    progress_total: int
    retry_count: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime
