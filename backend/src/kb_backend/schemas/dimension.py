from typing import Literal

from pydantic import BaseModel


class DimensionOut(BaseModel):
    key: str
    label: str
    field_type: Literal["text", "number", "date", "boolean"]
    weight: int

    model_config = {"from_attributes": True}
