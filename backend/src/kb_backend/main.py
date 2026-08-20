from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from kb_backend.auth.deps import auth_gate
from kb_backend.config import get_settings
from kb_backend.db import get_db
from kb_backend.envelope import BusinessError, envelope, register_exception_handlers
from kb_backend.relation_worker import start_relation_worker
from kb_backend.routers.audit_log import router as audit_log_router
from kb_backend.routers.auth import router as auth_router
from kb_backend.routers.category import router as category_router
from kb_backend.routers.dimension import router as dimension_router
from kb_backend.routers.knowledge_base import router as knowledge_base_router
from kb_backend.routers.knowledge_point import router as knowledge_point_router
from kb_backend.routers.relation import global_router as relation_global_router
from kb_backend.routers.relation import kp_router as relation_kp_router
from kb_backend.routers.user import router as user_router


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # 答案关联 worker：网关未配置时返回 None(功能降级为 disabled)。
    # 注意 TestClient(app) 不走 lifespan(只有 `with TestClient(...)` 才走)，
    # 所以现有测试不受影响，也绝不会在测试里意外起线程。
    worker = start_relation_worker()
    try:
        yield
    finally:
        if worker is not None:
            worker.stop()


# auth_gate 是全局依赖：每个请求先经 auth/roles.py 的规则表决定要求的
# 最低角色再放行（issue #36）。auth_mode=off（默认）时直通、行为与接入前
# 完全一致；unified 时校验 IDENTITYTOKEN。公开面（/health、第三方只读
# 对接面、OpenAPI 文档）在规则表里显式豁免。
app = FastAPI(title="Knowledge Base Backend", lifespan=_lifespan, dependencies=[Depends(auth_gate)])
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
    # DELETE added for issue "答案关联" 的 DELETE /answer-relations/{id} —
    # same explicit-list trap as the PUT note above.
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    # IDENTITYTOKEN / X-Identity-App-Type 是统一身份认证(#36)的自定义请求
    # 头——同上面 methods 的教训：不显式列出，浏览器预检直接失败，而
    # TestClient/curl 看不出任何问题。
    # X-Readonly-Token（万能只读 Token）与 X-Service-Token（服务间机器凭证）
    # 的主要调用方是服务端脚本（不经浏览器、无预检），列进来是为了浏览器侧
    # 联调/演示也能直接带头调用。
    allow_headers=[
        "Content-Type",
        "IDENTITYTOKEN",
        "X-Identity-App-Type",
        "X-Service-Token",
        "X-Readonly-Token",
    ],
)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(knowledge_base_router)
app.include_router(category_router)
app.include_router(dimension_router)
app.include_router(knowledge_point_router)
app.include_router(audit_log_router)
app.include_router(relation_kp_router)
app.include_router(relation_global_router)


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
