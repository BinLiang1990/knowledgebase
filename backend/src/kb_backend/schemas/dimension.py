from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DimensionOut(BaseModel):
    key: str
    label: str
    field_type: Literal["text", "number", "date", "boolean"]
    weight: int

    model_config = {"from_attributes": True}


# Internal admin view (issue #9 §2) — every dimension regardless of status,
# plus the fields the read-only external DimensionOut deliberately omits.
class DimensionAdminOut(BaseModel):
    key: str
    label: str
    field_type: Literal["text", "number", "date", "boolean"]
    weight: int
    default_value: str | None
    status: Literal["active", "deprecated"]
    answer_count: int

    model_config = {"from_attributes": True}


def _stripped_non_empty_label(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("名称不能为空")
    return v


class DimensionCreate(BaseModel):
    # max_length=100, not dimension_definition.label's real column width
    # (255) — on creation this value becomes BOTH `label` and `key` (design
    # doc §4.1: "填写 label(同时作为 key)"), and `key` is a String(100)
    # primary key. A value that fits `label`'s own column but not `key`'s
    # would otherwise pass this schema and then fail at the DB layer with
    # a confusing error.
    label: str = Field(min_length=1, max_length=100)
    field_type: Literal["text", "number", "date", "boolean"]
    weight: int = Field(default=50, ge=1, le=100)
    default_value: str | None = Field(default=None, max_length=255)

    @field_validator("label")
    @classmethod
    def _validate_label(cls, v: str) -> str:
        v = _stripped_non_empty_label(v)
        # This value becomes `key`, embedded as a single {key} path segment
        # in PATCH/activate/deactivate — a literal "/" splits into extra
        # path segments no route matches, and Starlette decodes a
        # percent-encoded "%2F" back to "/" *before* route matching, so
        # there is no way for a client to address such a key afterwards.
        # Rejecting it here is the only fix that doesn't require redesigning
        # those routes. Codex outer-gate finding on PR #25.
        if "/" in v:
            raise ValueError("名称不能包含斜杠(/)")
        return v


class DimensionUpdate(BaseModel):
    # field_type is deliberately absent — PRD §4.2: "field_type 创建后不可
    # 修改". Omitting it from the schema entirely (rather than accepting
    # and rejecting a changed value) makes it structurally impossible to
    # send, not just runtime-rejected.
    label: str | None = Field(default=None, min_length=1, max_length=255)
    weight: int | None = Field(default=None, ge=1, le=100)
    default_value: str | None = Field(default=None, max_length=255)

    @field_validator("label")
    @classmethod
    def _validate_label(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _stripped_non_empty_label(v)


class EnabledDimensionsUpdate(BaseModel):
    # No default — an explicit `[]` is how "clear everything" is spelled, so
    # an omitted field or a misspelled key name (e.g. "dimension_key") must
    # 422 instead of silently defaulting to that same empty list and wiping
    # every enabled dimension for the KB. Codex outer-gate finding on PR #25.
    dimension_keys: list[str]
