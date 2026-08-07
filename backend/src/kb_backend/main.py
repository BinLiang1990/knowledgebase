from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .db import get_db
from .envelope import BusinessError, envelope, register_exception_handlers

app = FastAPI(title="Knowledge Base Backend")
register_exception_handlers(app)


@app.get("/health")
def health(probe: int | None = None, db: Session = Depends(get_db)) -> dict:
    """Liveness/readiness check. `probe` is an optional strict-int query param
    with no functional effect — it exists so the 422 envelope path (an
    unparseable query value) has a real endpoint to exercise in tests without
    waiting for issue #2's business endpoints to land.
    """
    del probe
    try:
        db.execute(text("SELECT 1"))
    except OperationalError as exc:
        raise BusinessError("database unavailable", status_code=500) from exc
    return envelope({"database": "ok"})
