from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from kb_backend.config import get_settings
from kb_backend.db import get_db
from kb_backend.envelope import BusinessError, envelope, register_exception_handlers
from kb_backend.routers.audit_log import router as audit_log_router
from kb_backend.routers.dimension import router as dimension_router
from kb_backend.routers.knowledge_base import router as knowledge_base_router
from kb_backend.routers.knowledge_point import router as knowledge_point_router

app = FastAPI(title="Knowledge Base Backend")
register_exception_handlers(app)
# allow_methods/allow_headers must be explicit: CORSMiddleware's own
# defaults are allow_methods=("GET",) and allow_headers=() — every
# POST/PATCH request (create/edit/activate/deactivate) sends
# Content-Type: application/json, which triggers a preflight OPTIONS
# request that fails under those defaults. The middleware being present is
# not sufficient on its own; found during issue #6 design review before
# any frontend code was written, since this bug is invisible in code
# review and only shows up in a real browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_allowed_origin_list,
    # PUT added for issue #9's PUT .../enabled-dimensions — same "explicit
    # list, not the middleware's own GET-only default" trap as the original
    # comment above describes. Codex outer-gate finding on PR #25: this
    # endpoint worked fine against TestClient (no CORS involved) but every
    # real browser call would fail preflight.
    allow_methods=["GET", "POST", "PATCH", "PUT"],
    allow_headers=["Content-Type"],
)
app.include_router(knowledge_base_router)
app.include_router(dimension_router)
app.include_router(knowledge_point_router)
app.include_router(audit_log_router)


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


if __name__ == "__main__":
    # Lets this file be run directly (PyCharm's own ▶ gutter icon), as an
    # alternative to a separate `uvicorn kb_backend.main:app` run
    # configuration. `reload=True` needs the app passed as an import
    # string, not the `app` object itself — hence "kb_backend.main:app"
    # here rather than just `app`.
    import uvicorn

    uvicorn.run("kb_backend.main:app", host="127.0.0.1", port=8000, reload=True)
