from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ChangeLogEntryOut(BaseModel):
    time: datetime
    knowledge_point_id: int
    answer_id: int
    operator: str
    action: Literal["create", "edit", "revoke", "reactivate"]
    coord: dict[str, Any]
    before_content: str | None
    after_content: str | None
    source: str
    revoke_reason: str | None
    status: Literal["live", "superseded", "revoked", "reactivated"]
    revocable: bool
    reactivate_reason: str | None

    model_config = {"from_attributes": True}


class GlobalChangeLogEntryOut(ChangeLogEntryOut):
    knowledge_base_id: int
    knowledge_base_name: str
    knowledge_point_title: str
