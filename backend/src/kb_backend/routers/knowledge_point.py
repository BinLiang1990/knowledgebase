import json
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..change_log import build_change_log
from ..coord import CoordValueError, compute_coord_hash, normalize_coord
from ..db import get_db
from ..dimensions import get_enabled_dimension_types
from ..envelope import BusinessError, envelope
from ..models.answer import Answer
from ..models.knowledge_base import KnowledgeBase
from ..models.knowledge_point import KnowledgePoint
from ..resolve import ResolveResult, compute_all_answer_groups, compute_live_groups, resolve
from ..schemas.change_log import ChangeLogEntryOut
from ..schemas.knowledge_point import (
    AnswerCreate,
    AnswerEdit,
    AnswerGroupOut,
    AnswerOut,
    AnswerPromoteToDefault,
    AnswerRevoke,
    BatchImportItemResult,
    BatchImportResult,
    KnowledgePointBatchImportRequest,
    KnowledgePointCreate,
    KnowledgePointDeleteRequest,
    KnowledgePointOut,
    KnowledgePointUpdate,
    ResolvedOut,
)

router = APIRouter(prefix="/knowledge-bases/{kb_id}/knowledge-points", tags=["knowledge-point"])

_DUPLICATE_TITLE_MSG = "知识点标题已存在，请使用其他标题"
_KB_NOT_FOUND_MSG = "知识库不存在"
_KP_NOT_FOUND_MSG = "知识点不存在"
_ANSWER_NOT_FOUND_MSG = "答案不存在"
_MYSQL_ER_DUP_ENTRY = 1062


def _raise_if_duplicate_title(exc: IntegrityError) -> None:
    orig_args = getattr(exc.orig, "args", ())
    if orig_args and orig_args[0] == _MYSQL_ER_DUP_ENTRY:
        raise BusinessError(_DUPLICATE_TITLE_MSG, status_code=400) from exc
    raise exc


def _batch_item_failure_reason(exc: IntegrityError) -> str:
    # Unlike _raise_if_duplicate_title, this never re-raises: batch-import's
    # per-item loop (design doc §4.2, issue #11) must record any failure —
    # duplicate title or otherwise — as a failed result and keep processing
    # the rest of the batch, not let an unexpected IntegrityError propagate
    # and abort the whole request.
    orig_args = getattr(exc.orig, "args", ())
    if orig_args and orig_args[0] == _MYSQL_ER_DUP_ENTRY:
        return _DUPLICATE_TITLE_MSG
    return "写入失败（未知错误）"


def _get_kb_or_404(db: Session, kb_id: int) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise BusinessError(_KB_NOT_FOUND_MSG, status_code=404)
    return kb


def _get_kp_or_404(db: Session, kb_id: int, kp_id: int) -> KnowledgePoint:
    _get_kb_or_404(db, kb_id)
    kp = db.execute(
        select(KnowledgePoint).where(
            KnowledgePoint.id == kp_id, KnowledgePoint.knowledge_base_id == kb_id
        )
    ).scalar_one_or_none()
    if kp is None:
        raise BusinessError(_KP_NOT_FOUND_MSG, status_code=404)
    return kp


def _ensure_title_available(db: Session, kb_id: int, title: str, exclude_id: int | None = None) -> None:
    stmt = select(KnowledgePoint.id).where(
        KnowledgePoint.knowledge_base_id == kb_id, KnowledgePoint.title == title
    )
    if exclude_id is not None:
        stmt = stmt.where(KnowledgePoint.id != exclude_id)
    if db.execute(stmt).first() is not None:
        raise BusinessError(_DUPLICATE_TITLE_MSG, status_code=400)


def _chain_is_revoked(db: Session, kp_id: int, coord_hash: str) -> bool:
    # Revocation is a whole-chain property (PRD §6 rule #4): every row
    # sharing a coord_hash is revoked together, so "any row revoked" is an
    # equivalent, cheaper check than "all rows revoked". Writing a new
    # (non-revoked) row under an already-revoked coord_hash would otherwise
    # silently resurrect a dead chain — no un-revoke feature exists in P0.
    # Found by the Codex outer-gate review on PR #20 (round 2).
    return (
        db.execute(
            select(Answer.id)
            .where(Answer.knowledge_point_id == kp_id, Answer.coord_hash == coord_hash, Answer.revoked.is_(True))
            .limit(1)
        ).first()
        is not None
    )


def _get_active_answer_count(db: Session, kp_id: int) -> int:
    return db.execute(
        select(func.count())
        .select_from(Answer)
        .where(Answer.knowledge_point_id == kp_id, Answer.revoked.is_(False))
    ).scalar_one()


def _to_kp_out(kp: KnowledgePoint, active_answer_count: int) -> KnowledgePointOut:
    return KnowledgePointOut(
        id=kp.id,
        knowledge_base_id=kp.knowledge_base_id,
        title=kp.title,
        status=kp.status,
        operator=kp.operator,
        active_answer_count=active_answer_count,
        created_at=kp.created_at,
        updated_at=kp.updated_at,
        deleted_at=kp.deleted_at,
        delete_reason=kp.delete_reason,
    )


def _to_answer_out(answer: Answer) -> AnswerOut:
    return AnswerOut.model_validate(answer)


def _to_resolved_out(result: ResolveResult) -> ResolvedOut:
    return ResolvedOut(status=result.status, answer=_to_answer_out(result.answer) if result.answer else None)


def _parse_query_coord(db: Session, kb_id: int, coord_param: str | None) -> dict[str, Any]:
    """Query conditions go through the exact same normalize_coord() +
    enabled-dimension check as write-path coord (docs/PRD.md §4.2: 精确相等
    匹配 applies identically to both). `coord_param` is a JSON object encoded
    as a query string, e.g. ?coord={"tenant":"acme"} — a GET request has no
    body, and the key set varies per KB, so a flat list of query params
    can't represent it."""
    if coord_param is None:
        return {}
    try:
        parsed = json.loads(coord_param)
    except json.JSONDecodeError as exc:
        raise BusinessError("coord 参数不是合法的 JSON", status_code=422) from exc
    if not isinstance(parsed, dict):
        raise BusinessError("coord 参数必须是一个 JSON 对象", status_code=422)

    dimension_types = get_enabled_dimension_types(db, kb_id)
    try:
        return normalize_coord(parsed, dimension_types)
    except CoordValueError as exc:
        raise BusinessError(str(exc), status_code=400) from exc


@router.post("")
def create_knowledge_point(
    kb_id: int, payload: KnowledgePointCreate, db: Session = Depends(get_db)
) -> dict:
    _get_kb_or_404(db, kb_id)
    _ensure_title_available(db, kb_id, payload.title)

    kp = KnowledgePoint(knowledge_base_id=kb_id, title=payload.title, status="active", operator="admin")
    db.add(kp)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        _raise_if_duplicate_title(exc)

    active_answer_count = 0
    if payload.default_answer is not None:
        empty_coord: dict = {}
        answer = Answer(
            knowledge_base_id=kb_id,
            knowledge_point_id=kp.id,
            coord=empty_coord,
            coord_hash=compute_coord_hash(empty_coord),
            content=payload.default_answer.content,
            effective_time=payload.default_answer.effective_time,
            note=payload.default_answer.note,
            operator="admin",
            source="人工填报",
        )
        db.add(answer)
        active_answer_count = 1

    db.commit()
    db.refresh(kp)
    out = _to_kp_out(kp, active_answer_count)
    return envelope(out.model_dump(mode="json"))


@router.post("/batch-import")
def batch_import_knowledge_points(
    kb_id: int, payload: KnowledgePointBatchImportRequest, db: Session = Depends(get_db)
) -> dict:
    """批量导入 (issue #11, design doc §4.1/§4.2) — 部分成功，逐项报告结果。
    每个 item 包在一个 SAVEPOINT (db.begin_nested()) 里；SAVEPOINT 块内部不做
    任何 try/except，让异常原样传播出去交给 begin_nested() 自己的上下文管理器
    完成 ROLLBACK TO SAVEPOINT —— 绝不能在块内手动调用 db.rollback()（那会
    回滚最外层事务，冲掉同批次前面已经成功、还未 commit 的 item）。这是对抗
    式审查在设计阶段抓到的阻塞级问题。

    per-item 的 except 只捕获 IntegrityError（标题重复等约束冲突——只回滚到
    这一条自己的 SAVEPOINT，不影响外层事务）和 BusinessError（同理），刻意
    不加一个兜底的 `except Exception`：MySQL 死锁 (`OperationalError`) 之类
    会让整个外层事务失效的错误，绝不能被当成"这一条失败、继续下一条"处理——
    这种错误发生时，前面已经 RELEASE SAVEPOINT 的 item 也会随外层事务一起被
    数据库回滚，如果继续把它们当成成功写进 results，最终返回的就是一份声称
    "已创建"、但实际数据库里根本不存在的虚假结果。让这类异常原样往外传播、
    在到达 db.commit() 之前中断整个请求，交给项目已有的全局异常处理器
    (envelope.register_exception_handlers 的 _unhandled_exception_handler)
    转换成标准的 500——同一个数据库会话从未 commit，session.close() 会丢弃
    所有未提交的写入，不会残留部分数据。Codex 外门审查在 PR #27 抓到的问题。
    """
    _get_kb_or_404(db, kb_id)

    results: list[BatchImportItemResult] = []
    created_count = 0

    for index, item in enumerate(payload.items):
        try:
            with db.begin_nested():
                _ensure_title_available(db, kb_id, item.title)
                kp = KnowledgePoint(knowledge_base_id=kb_id, title=item.title, status="active", operator="admin")
                db.add(kp)
                db.flush()

                if item.default_answer is not None:
                    empty_coord: dict = {}
                    db.add(
                        Answer(
                            knowledge_base_id=kb_id,
                            knowledge_point_id=kp.id,
                            coord=empty_coord,
                            coord_hash=compute_coord_hash(empty_coord),
                            content=item.default_answer.content,
                            effective_time=item.default_answer.effective_time,
                            note=item.default_answer.note,
                            operator="admin",
                            source="人工填报",
                        )
                    )
                    db.flush()
        except IntegrityError as exc:
            results.append(
                BatchImportItemResult(
                    index=index, status="failed", title=item.title, reason=_batch_item_failure_reason(exc)
                )
            )
            continue
        except BusinessError as exc:
            results.append(
                BatchImportItemResult(index=index, status="failed", title=item.title, reason=exc.message)
            )
            continue

        created_count += 1
        results.append(
            BatchImportItemResult(index=index, status="created", title=item.title, knowledge_point_id=kp.id)
        )

    db.commit()

    out = BatchImportResult(
        created_count=created_count, failed_count=len(results) - created_count, results=results
    )
    return envelope(out.model_dump(mode="json"))


@router.get("")
def list_knowledge_points(
    kb_id: int,
    status: Literal["active", "deleted"] = Query(default="active"),
    # max_length=255 matches knowledge_point.title's own VARCHAR(255) — an
    # unbounded keyword fed straight into a SQL LIKE is a trivial CPU/memory
    # DoS vector. Found by the Kimi review gate on PR #21.
    keyword: str | None = Query(default=None, max_length=255),
    at: date | None = Query(default=None),
    coord: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    _get_kb_or_404(db, kb_id)
    at = at or date.today()
    query_coord = _parse_query_coord(db, kb_id, coord)

    count_by_kp = dict(
        db.execute(
            select(Answer.knowledge_point_id, func.count())
            .where(Answer.knowledge_base_id == kb_id, Answer.revoked.is_(False))
            .group_by(Answer.knowledge_point_id)
        ).all()
    )

    stmt = select(KnowledgePoint).where(
        KnowledgePoint.knowledge_base_id == kb_id, KnowledgePoint.status == status
    )
    # Guard on the STRIPPED value, not the raw one: a whitespace-only
    # keyword (e.g. "   ") is truthy but strips to "", and contains("")
    # matches every title — silently disabling filtering instead of either
    # filtering or erroring. Found by the Kimi review gate on PR #21.
    stripped_keyword = keyword.strip() if keyword else ""
    if stripped_keyword:
        # Case-insensitive substring match, mirroring frontend-mock's
        # kp.title.toLowerCase().includes(S.kw) — done in the query rather
        # than in Python so it's not fetching rows we'll immediately drop.
        # autoescape=True: without it, a literal "%" or "_" in the keyword
        # is interpreted as a SQL LIKE wildcard instead of a literal
        # character, diverging from JS .includes()'s literal-substring
        # semantics. Found by the Codex outer-gate review on PR #21.
        stmt = stmt.where(func.lower(KnowledgePoint.title).contains(stripped_keyword.lower(), autoescape=True))
    rows = db.execute(stmt.order_by(KnowledgePoint.id)).scalars().all()

    out = []
    for kp in rows:
        groups = compute_live_groups(db, kb_id, kp.id, at)
        resolved = resolve(groups, query_coord)
        # Only a non-empty query condition excludes non-matching knowledge
        # points from the list; with no condition, every keyword-matching KP
        # is shown regardless of its resolved status (docs/specs/
        # 2026-08-08-resolve-engine-design.md §4.2, mirroring
        # frontend-mock's visibleKps(): hasQ gates this, not resolved.status
        # on its own).
        if query_coord and resolved.status == "none":
            continue
        kp_out = _to_kp_out(kp, count_by_kp.get(kp.id, 0)).model_dump(mode="json")
        kp_out["resolved"] = _to_resolved_out(resolved).model_dump(mode="json")
        out.append(kp_out)
    return envelope(out)


@router.get("/{kp_id}/resolve")
def resolve_knowledge_point(
    kb_id: int,
    kp_id: int,
    at: date | None = Query(default=None),
    coord: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    kp = _get_kp_or_404(db, kb_id, kp_id)
    at = at or date.today()
    query_coord = _parse_query_coord(db, kb_id, coord)

    if kp.status == "deleted":
        # PRD §4.4: a soft-deleted knowledge point must not appear in query
        # results (its retained answers are for the recycle-bin/restore
        # flow only, not for this externally-facing resolve endpoint).
        # Behaves like "no answers exist" rather than 404 — this endpoint's
        # own contract is "always 200 + a status field" for any KP that
        # does genuinely exist. Found by the Codex outer-gate review on
        # PR #21.
        return envelope(_to_resolved_out(ResolveResult(status="none", answer=None)).model_dump(mode="json"))

    groups = compute_live_groups(db, kb_id, kp_id, at)
    result = resolve(groups, query_coord)
    return envelope(_to_resolved_out(result).model_dump(mode="json"))


@router.get("/{kp_id}/answer-groups")
def list_answer_groups(
    kb_id: int,
    kp_id: int,
    at: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Read-only, all-conditions view for the expandable answer tree
    (issue #7) — every coord group this knowledge point has ever had, not
    just the single best-matching one `resolve` returns. Deliberately uses
    compute_all_answer_groups(), not compute_live_groups(): the latter
    drops whole-chain-revoked groups outright, but the tree must still show
    them (struck through) per PRD §4.4's "全部答案的分组树".

    Deliberately does NOT special-case a soft-deleted knowledge point the
    way resolve_knowledge_point does. That endpoint's "none" contract is for
    third-party query consumers, where a deleted KP correctly has no answer.
    This one backs the detail page's answer tree/current-answers view, which
    PRD §4.7 requires to keep showing a deleted KP's full historical answers
    ("以下仍可查看其全部历史答案") — issue #8's Codex outer-gate review found
    the original short-circuit here (copied from the resolve endpoint
    without re-checking whether it applied) silently emptied that view.
    """
    kp = _get_kp_or_404(db, kb_id, kp_id)
    at = at or date.today()

    groups = compute_all_answer_groups(db, kb_id, kp_id, at)
    out = [
        AnswerGroupOut(
            coord=g.coord,
            revoked=g.revoked,
            version_count=g.version_count,
            latest_answer=_to_answer_out(g.latest_answer),
            live_answer=_to_answer_out(g.live_answer) if g.live_answer else None,
        ).model_dump(mode="json")
        for g in groups
    ]
    return envelope(out)


@router.get("/{kp_id}")
def get_knowledge_point(kb_id: int, kp_id: int, db: Session = Depends(get_db)) -> dict:
    kp = _get_kp_or_404(db, kb_id, kp_id)
    count = _get_active_answer_count(db, kp_id)
    return envelope(_to_kp_out(kp, count).model_dump(mode="json"))


@router.get("/{kp_id}/change-log")
def get_change_log(kb_id: int, kp_id: int, db: Session = Depends(get_db)) -> dict:
    """变更留痕 (issue #12, design doc §4.1) — this knowledge point's whole
    answer history reduced to a write-order timeline. Deliberately does NOT
    special-case a soft-deleted knowledge point the way create_answer/
    edit_answer do — this is a read-only audit view, not a "write new
    content" operation, so a deleted KP's history remains fully visible
    (mirrors list_answer_groups' own precedent)."""
    _get_kp_or_404(db, kb_id, kp_id)
    answers = (
        db.execute(
            select(Answer).where(Answer.knowledge_base_id == kb_id, Answer.knowledge_point_id == kp_id)
        )
        .scalars()
        .all()
    )
    entries = build_change_log(list(answers))
    out = [ChangeLogEntryOut.model_validate(e).model_dump(mode="json") for e in entries]
    return envelope(out)


@router.patch("/{kp_id}")
def update_knowledge_point(
    kb_id: int, kp_id: int, payload: KnowledgePointUpdate, db: Session = Depends(get_db)
) -> dict:
    kp = _get_kp_or_404(db, kb_id, kp_id)
    if kp.status == "deleted":
        # Consistent with create_answer/edit_answer's own guard — a
        # soft-deleted knowledge point is read-only everywhere except the
        # delete/restore actions themselves. The frontend detail page
        # (issue #8) already hides the "编辑标题" button for a deleted KP;
        # this closes the same gap at the API level so a direct PATCH can't
        # bypass it. Kimi 终审 finding on PR #24.
        raise BusinessError("知识点已删除，无法编辑标题", status_code=400)

    if payload.title != kp.title:
        _ensure_title_available(db, kb_id, payload.title, exclude_id=kp_id)
        kp.title = payload.title

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_if_duplicate_title(exc)
    db.refresh(kp)

    count = _get_active_answer_count(db, kp_id)
    return envelope(_to_kp_out(kp, count).model_dump(mode="json"))


@router.post("/{kp_id}/delete")
def delete_knowledge_point(
    kb_id: int, kp_id: int, payload: KnowledgePointDeleteRequest, db: Session = Depends(get_db)
) -> dict:
    kp = _get_kp_or_404(db, kb_id, kp_id)
    if kp.status != "deleted":
        # Idempotent, but a retry's reason never overwrites the reason
        # recorded the first time this KP was actually deleted.
        kp.status = "deleted"
        kp.deleted_at = func.now()
        kp.delete_reason = payload.delete_reason
        db.commit()
        db.refresh(kp)

    count = _get_active_answer_count(db, kp_id)
    return envelope(_to_kp_out(kp, count).model_dump(mode="json"))


@router.post("/{kp_id}/restore")
def restore_knowledge_point(kb_id: int, kp_id: int, db: Session = Depends(get_db)) -> dict:
    kp = _get_kp_or_404(db, kb_id, kp_id)
    if kp.status != "active":
        # deleted_at/delete_reason are deliberately left in place as history,
        # not cleared — nothing in the PRD asks for them to be wiped.
        kp.status = "active"
        db.commit()
        db.refresh(kp)

    count = _get_active_answer_count(db, kp_id)
    return envelope(_to_kp_out(kp, count).model_dump(mode="json"))


@router.post("/{kp_id}/answers")
def create_answer(kb_id: int, kp_id: int, payload: AnswerCreate, db: Session = Depends(get_db)) -> dict:
    kp = _get_kp_or_404(db, kb_id, kp_id)
    if kp.status == "deleted":
        raise BusinessError("知识点已删除，无法写入答案", status_code=400)

    dimension_types = get_enabled_dimension_types(db, kb_id)
    try:
        normalized = normalize_coord(payload.coord, dimension_types)
    except CoordValueError as exc:
        raise BusinessError(str(exc), status_code=400) from exc

    coord_hash = compute_coord_hash(normalized)
    if _chain_is_revoked(db, kp_id, coord_hash):
        raise BusinessError("该条件组合已被撤回，无法直接写入", status_code=400)

    answer = Answer(
        knowledge_base_id=kb_id,
        knowledge_point_id=kp_id,
        coord=normalized,
        coord_hash=coord_hash,
        content=payload.content,
        effective_time=payload.effective_time,
        note=payload.note,
        operator="admin",
        source="人工填报",
    )
    db.add(answer)
    db.commit()
    db.refresh(answer)
    return envelope(_to_answer_out(answer).model_dump(mode="json"))


@router.post("/{kp_id}/answers/{answer_id}/edit")
def edit_answer(
    kb_id: int, kp_id: int, answer_id: int, payload: AnswerEdit, db: Session = Depends(get_db)
) -> dict:
    kp = _get_kp_or_404(db, kb_id, kp_id)
    if kp.status == "deleted":
        raise BusinessError("知识点已删除，无法编辑答案", status_code=400)

    target = db.execute(
        select(Answer).where(
            Answer.id == answer_id,
            Answer.knowledge_point_id == kp_id,
            Answer.knowledge_base_id == kb_id,
        )
    ).scalar_one_or_none()
    if target is None:
        raise BusinessError(_ANSWER_NOT_FOUND_MSG, status_code=404)
    if target.revoked:
        raise BusinessError("该条件组合已被撤回，无法编辑", status_code=400)

    fields_set = payload.model_fields_set
    if "coord" in fields_set:
        # payload.coord is guaranteed a dict here, never None — the schema's
        # own validator rejects an explicit JSON null before this point.
        dimension_types = get_enabled_dimension_types(db, kb_id)
        try:
            new_normalized = normalize_coord(payload.coord, dimension_types)
        except CoordValueError as exc:
            raise BusinessError(str(exc), status_code=400) from exc
        new_hash = compute_coord_hash(new_normalized)
    else:
        # Coord omitted: reuse the target chain's own coord verbatim, with
        # zero re-validation — a dimension disabled after the fact must not
        # break appending to a chain that already used it (PRD §6 rule #7).
        new_normalized = target.coord
        new_hash = target.coord_hash

    is_migration = new_hash != target.coord_hash

    if is_migration:
        if _chain_is_revoked(db, kp_id, new_hash):
            raise BusinessError("目标条件组合已被撤回，无法迁移到该条件", status_code=400)
        reason = (payload.migration_reason or "").strip()
        if not reason:
            raise BusinessError("变更适用条件需要填写迁移原因", status_code=400)
        db.execute(
            update(Answer)
            .where(Answer.knowledge_point_id == kp_id, Answer.coord_hash == target.coord_hash)
            .values(revoked=True, revoked_at=func.now(), revoked_by="admin", revoke_reason=reason)
        )

    new_answer = Answer(
        knowledge_base_id=kb_id,
        knowledge_point_id=kp_id,
        coord=new_normalized,
        coord_hash=new_hash,
        content=payload.content,
        effective_time=payload.effective_time,
        note=payload.note,
        operator="admin",
        source="人工编辑",
    )
    db.add(new_answer)
    db.commit()
    db.refresh(new_answer)
    return envelope(_to_answer_out(new_answer).model_dump(mode="json"))


def _get_answer_or_404(db: Session, kb_id: int, kp_id: int, answer_id: int) -> Answer:
    answer = db.execute(
        select(Answer).where(
            Answer.id == answer_id,
            Answer.knowledge_point_id == kp_id,
            Answer.knowledge_base_id == kb_id,
        )
    ).scalar_one_or_none()
    if answer is None:
        raise BusinessError(_ANSWER_NOT_FOUND_MSG, status_code=404)
    return answer


@router.post("/{kp_id}/answers/{answer_id}/promote-to-default")
def promote_answer_to_default(
    kb_id: int, kp_id: int, answer_id: int, payload: AnswerPromoteToDefault, db: Session = Depends(get_db)
) -> dict:
    """"设为默认" (issue #10, design doc §4.2/§4.3) — copies `answer_id`'s
    *content* into a brand-new version of the default (coord={}) chain.
    The source answer itself is never touched. Functionally this is
    create_answer with coord hard-coded to {} and content read server-side
    instead of client-supplied, so it shares create_answer's own two
    guards (deleted KP, revoked target chain) rather than inventing new
    ones."""
    kp = _get_kp_or_404(db, kb_id, kp_id)
    if kp.status == "deleted":
        raise BusinessError("知识点已删除，无法写入答案", status_code=400)

    source = _get_answer_or_404(db, kb_id, kp_id, answer_id)

    default_hash = compute_coord_hash({})
    if _chain_is_revoked(db, kp_id, default_hash):
        raise BusinessError("该条件组合已被撤回，无法直接写入", status_code=400)

    promoted = Answer(
        knowledge_base_id=kb_id,
        knowledge_point_id=kp_id,
        coord={},
        coord_hash=default_hash,
        content=source.content,
        effective_time=payload.effective_time,
        note=payload.note,
        operator="admin",
        source="人工填报",
    )
    db.add(promoted)
    db.commit()
    db.refresh(promoted)
    return envelope(_to_answer_out(promoted).model_dump(mode="json"))


@router.post("/{kp_id}/answers/{answer_id}/revoke")
def revoke_answer(
    kb_id: int, kp_id: int, answer_id: int, payload: AnswerRevoke, db: Session = Depends(get_db)
) -> dict:
    """撤回 (issue #10, design doc §4.1/§4.4/§4.5) — whole-chain logical
    delete, keyed by any answer_id in that chain (mirrors edit_answer's own
    answer_id-based targeting, not a client-supplied coord dict). Doesn't
    gate on the knowledge point's deleted status — PRD §6 rule #8 treats KP
    soft-delete and answer revocation as independent, unlike create/edit
    answer's "no new content on a deleted KP" rule."""
    _get_kp_or_404(db, kb_id, kp_id)
    target = _get_answer_or_404(db, kb_id, kp_id, answer_id)

    # The "first reason wins" idempotency guarantee (§4.5) must be enforced
    # by the UPDATE's WHERE clause itself, not by a check-then-act `if not
    # target.revoked` gate in Python: two concurrent requests can both read
    # revoked=False before either commits, and without the revoked=False
    # filter here both UPDATEs would apply, with the second commit
    # overwriting the first's revoked_at/revoked_by/revoke_reason (Kimi
    # 终审 finding, issue #10). The knowledge_point_id filter is separately
    # load-bearing — compute_coord_hash is a pure function of the
    # normalized coord alone, so coord_hash collides across every KP that
    # shares a coord (guaranteed for coord={}). Without it, revoking one
    # KP's default-answer chain would silently revoke every KP's. Design
    # doc §3 — found by adversarial review before this endpoint was
    # written.
    db.execute(
        update(Answer)
        .where(
            Answer.knowledge_point_id == kp_id,
            Answer.coord_hash == target.coord_hash,
            Answer.revoked.is_(False),
        )
        .values(
            revoked=True,
            revoked_at=func.now(),
            revoked_by="admin",
            revoke_reason=payload.revoke_reason,
        )
    )
    db.commit()
    db.refresh(target)

    return envelope(_to_answer_out(target).model_dump(mode="json"))
