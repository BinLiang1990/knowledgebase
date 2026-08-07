from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..envelope import envelope
from ..models.dimension import DimensionDefinition
from ..schemas.dimension import DimensionOut

router = APIRouter(tags=["dimension"])


@router.get("/dimensions")
def list_dimensions(db: Session = Depends(get_db)) -> dict:
    rows = (
        db.execute(
            select(DimensionDefinition)
            .where(DimensionDefinition.status == "active")
            .order_by(DimensionDefinition.key)
        )
        .scalars()
        .all()
    )
    out = [DimensionOut.model_validate(row) for row in rows]
    return envelope([o.model_dump(mode="json") for o in out])
