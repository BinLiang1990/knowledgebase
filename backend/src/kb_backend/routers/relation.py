"""答案关联 API（docs/PRD-答案关联.md §3）。

两组路由：
- kp_router：挂在知识点下——发起分析、查询该知识点的全部关联；
- global_router：跨知识点的操作——任务进度、手动添加、编辑描述、删除。
  关联本身跨知识库，挂在单个 kb/kp 前缀下语义不通（PRD §3.3）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..auth.deps import current_operator
from ..config import get_settings
from ..db import get_db
from ..envelope import BusinessError, envelope
from ..models.knowledge_base import KnowledgeBase
from ..models.knowledge_point import KnowledgePoint
from ..models.relation import AnswerRelation, RelationTask
from ..relations import (
    ChainEndpoint,
    collect_endpoints,
    find_relation,
    normalize_pair,
    schedule_analyze_task,
    schedule_generate_pair_task,
)
from ..schemas.relation import (
    AnalyzeRequest,
    EndpointRef,
    RelationCreate,
    RelationEndpointOut,
    RelationOut,
    RelationsOut,
    RelationUpdate,
    TaskOut,
)
from .knowledge_point import _get_kp_or_404

kp_router = APIRouter(
    prefix="/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answer-relations", tags=["answer-relation"]
)
global_router = APIRouter(prefix="/answer-relations", tags=["answer-relation"])

_RELATION_NOT_FOUND_MSG = "关联不存在"
_ANALYSIS_DISABLED_MSG = "关联分析未启用（服务端未配置模型网关）"
_PREVIEW_CHARS = 200


# ---------------- 发起分析 ----------------

@kp_router.post("/analyze")
def analyze(kb_id: int, kp_id: int, payload: AnalyzeRequest, db: Session = Depends(get_db)) -> dict:
    _get_kp_or_404(db, kb_id, kp_id)
    if not get_settings().relation_analysis_enabled:
        raise BusinessError(_ANALYSIS_DISABLED_MSG)

    endpoints = collect_endpoints(db, kp_id=kp_id)
    if payload.coord_hash is not None and not any(ep.coord_hash == payload.coord_hash for ep in endpoints):
        raise BusinessError("该条件当前没有生效答案，无法分析")
    if not endpoints:
        raise BusinessError("当前没有生效答案，无法分析")

    task = schedule_analyze_task(db, kb_id, kp_id, payload.coord_hash, operator=current_operator())
    db.commit()
    db.refresh(task)
    return envelope({"task_id": task.id, "status": task.status})


@global_router.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)) -> dict:
    task = db.get(RelationTask, task_id)
    if task is None:
        raise BusinessError("任务不存在", status_code=404)
    return envelope(TaskOut.model_validate(task).model_dump(mode="json"))


# ---------------- 查询 ----------------

def _endpoint_infos(
    db: Session, refs: list[tuple[int, int, str]]
) -> dict[tuple[int, str], dict]:
    """批量解析端点展示信息：kb 名称、kp 标题、状态、当前生效内容。
    collect_endpoints 只返回"知识点未删除且链有生效版本"的端点，所以
    缺席即可推导 revoked / kp-deleted / missing 三种灰态（PRD §3.6）。"""
    kp_ids = {kp_id for _, kp_id, _ in refs}
    kb_ids = {kb_id for kb_id, _, _ in refs}
    kps = {k.id: k for k in db.execute(select(KnowledgePoint).where(KnowledgePoint.id.in_(kp_ids))).scalars()}
    kbs = {b.id: b for b in db.execute(select(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids))).scalars()}
    live: dict[tuple[int, str], ChainEndpoint] = {}
    for kp_id in kp_ids:
        for ep in collect_endpoints(db, kp_id=kp_id):
            live[ep.key] = ep

    infos: dict[tuple[int, str], dict] = {}
    for kb_id, kp_id, coord_hash in refs:
        kp = kps.get(kp_id)
        kb = kbs.get(kb_id)
        ep = live.get((kp_id, coord_hash))
        if kp is None or kb is None:
            state = "missing"
        elif kp.status == "deleted":
            state = "kp-deleted"
        elif ep is None:
            state = "revoked"
        else:
            state = "ok"
        infos[(kp_id, coord_hash)] = {
            "kb_name": kb.name if kb else None,
            "kp_title": kp.title if kp else None,
            "state": state,
            "live": ep,
        }
    return infos


def _relation_out(rel: AnswerRelation, infos: dict[tuple[int, str], dict]) -> RelationOut:
    def endpoint_out(kb_id: int, kp_id: int, coord_hash: str, coord: dict) -> RelationEndpointOut:
        info = infos[(kp_id, coord_hash)]
        ep: ChainEndpoint | None = info["live"]
        return RelationEndpointOut(
            kb_id=kb_id, kp_id=kp_id, coord_hash=coord_hash, coord=coord,
            kb_name=info["kb_name"], kp_title=info["kp_title"], state=info["state"],
            current_content_preview=ep.content[:_PREVIEW_CHARS] if ep else None,
        )

    a = endpoint_out(rel.kb_a_id, rel.kp_a_id, rel.coord_hash_a, rel.coord_a)
    b = endpoint_out(rel.kb_b_id, rel.kp_b_id, rel.coord_hash_b, rel.coord_b)
    live_a = infos[(rel.kp_a_id, rel.coord_hash_a)]["live"]
    live_b = infos[(rel.kp_b_id, rel.coord_hash_b)]["live"]
    stale = bool(
        (live_a is not None and rel.content_hash_a is not None and live_a.content_hash != rel.content_hash_a)
        or (live_b is not None and rel.content_hash_b is not None and live_b.content_hash != rel.content_hash_b)
    )
    return RelationOut(
        id=rel.id, a=a, b=b, description=rel.description, source=rel.source,
        similarity=rel.similarity, model=rel.model, operator=rel.operator,
        stale=stale, generating=(rel.description == ""),
        created_at=rel.created_at, updated_at=rel.updated_at,
    )


@kp_router.get("")
def list_relations(
    kb_id: int,
    kp_id: int,
    coord_hash: str | None = Query(default=None, min_length=64, max_length=64),
    db: Session = Depends(get_db),
) -> dict:
    """该知识点的全部关联（任一端属于该知识点即返回，两端对称可见）。
    刻意不对已软删除的知识点短路——关联与历史答案一样"永久可查"。"""
    _get_kp_or_404(db, kb_id, kp_id)

    stmt = select(AnswerRelation).where(
        or_(AnswerRelation.kp_a_id == kp_id, AnswerRelation.kp_b_id == kp_id)
    )
    if coord_hash is not None:
        stmt = select(AnswerRelation).where(
            or_(
                (AnswerRelation.kp_a_id == kp_id) & (AnswerRelation.coord_hash_a == coord_hash),
                (AnswerRelation.kp_b_id == kp_id) & (AnswerRelation.coord_hash_b == coord_hash),
            )
        )
    rels = db.execute(stmt.order_by(AnswerRelation.id)).scalars().all()

    refs = [(r.kb_a_id, r.kp_a_id, r.coord_hash_a) for r in rels] + [
        (r.kb_b_id, r.kp_b_id, r.coord_hash_b) for r in rels
    ]
    infos = _endpoint_infos(db, refs)

    if not get_settings().relation_analysis_enabled:
        generation_status = "disabled"
    else:
        active = db.execute(
            select(RelationTask.status).where(
                RelationTask.knowledge_point_id == kp_id,
                RelationTask.status.in_(("pending", "generating")),
            )
        ).scalars().all()
        generation_status = "generating" if "generating" in active else ("pending" if active else "idle")

    out = RelationsOut(
        generation_status=generation_status,
        relations=[_relation_out(r, infos) for r in rels],
    )
    return envelope(out.model_dump(mode="json"))


# ---------------- 手动添加 / 编辑 / 删除 ----------------

def _resolve_live_endpoint(db: Session, ref: EndpointRef) -> ChainEndpoint:
    kb = db.get(KnowledgeBase, ref.kb_id)
    if kb is None:
        raise BusinessError("知识库不存在", status_code=404)
    kp = db.execute(
        select(KnowledgePoint).where(
            KnowledgePoint.id == ref.kp_id, KnowledgePoint.knowledge_base_id == ref.kb_id
        )
    ).scalar_one_or_none()
    if kp is None:
        raise BusinessError("知识点不存在", status_code=404)
    ep = next(
        (e for e in collect_endpoints(db, kp_id=ref.kp_id) if e.coord_hash == ref.coord_hash), None
    )
    if ep is None:
        raise BusinessError(f"知识点「{kp.title}」所选条件当前没有生效答案（可能已撤回）")
    return ep


@global_router.post("")
def create_relation(payload: RelationCreate, db: Session = Depends(get_db)) -> dict:
    x = _resolve_live_endpoint(db, payload.a)
    y = _resolve_live_endpoint(db, payload.b)
    if x.key == y.key:
        raise BusinessError("不能与自身建立关联，请选择两条不同的答案")
    if find_relation(db, x, y) is not None:
        raise BusinessError("这两条答案之间已存在关联，可在列表中编辑或删除")

    description = (payload.description or "").strip()
    if not description and not payload.generate:
        raise BusinessError("请填写关联描述，或选择由 AI 生成")
    if not description and payload.generate and not get_settings().relation_analysis_enabled:
        raise BusinessError(_ANALYSIS_DISABLED_MSG)

    a, b = normalize_pair(x, y)
    rel = AnswerRelation(
        kb_a_id=a.kb_id, kp_a_id=a.kp_id, coord_hash_a=a.coord_hash, coord_a=a.coord,
        kb_b_id=b.kb_id, kp_b_id=b.kp_id, coord_hash_b=b.coord_hash, coord_b=b.coord,
        answer_a_id=a.answer_id, answer_b_id=b.answer_id,
        content_hash_a=a.content_hash, content_hash_b=b.content_hash,
        description=description,
        # 空描述 + generate：先落 ai 空壳，worker 填充；人工描述 = manual
        source="manual" if description else "ai",
        operator=current_operator(),
    )
    db.add(rel)
    db.flush()

    task_id = None
    if not description:
        task = schedule_generate_pair_task(db, a.kb_id, a.kp_id, rel.id, operator=current_operator())
        db.flush()
        task_id = task.id
    db.commit()
    return envelope({"relation_id": rel.id, "task_id": task_id})


@global_router.patch("/{relation_id}")
def update_relation(relation_id: int, payload: RelationUpdate, db: Session = Depends(get_db)) -> dict:
    rel = db.get(AnswerRelation, relation_id)
    if rel is None:
        raise BusinessError(_RELATION_NOT_FOUND_MSG, status_code=404)
    rel.description = payload.description.strip()
    if not rel.description:
        raise BusinessError("描述不能为空")
    # 人工改写后转 manual，后续 AI 分析不再覆盖（PRD §3.4）
    rel.source = "manual"
    rel.model = None
    db.commit()
    return envelope({"relation_id": rel.id})


@global_router.post("/{relation_id}/regenerate")
def regenerate_relation(relation_id: int, db: Session = Depends(get_db)) -> dict:
    """单对重新生成（PRD §3.5）：重新生成即接受 AI 内容，完成后 source 转回 ai。"""
    rel = db.get(AnswerRelation, relation_id)
    if rel is None:
        raise BusinessError(_RELATION_NOT_FOUND_MSG, status_code=404)
    if not get_settings().relation_analysis_enabled:
        raise BusinessError(_ANALYSIS_DISABLED_MSG)
    task = schedule_generate_pair_task(db, rel.kb_a_id, rel.kp_a_id, rel.id, operator=current_operator())
    db.commit()
    db.refresh(task)
    return envelope({"task_id": task.id, "status": task.status})


@global_router.delete("/{relation_id}")
def delete_relation(relation_id: int, db: Session = Depends(get_db)) -> dict:
    rel = db.get(AnswerRelation, relation_id)
    if rel is None:
        raise BusinessError(_RELATION_NOT_FOUND_MSG, status_code=404)
    db.delete(rel)
    db.commit()
    return envelope({})
