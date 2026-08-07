from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..coord import CoordValueError, compute_coord_hash, normalize_coord
from ..db import get_db
from ..dimensions import get_enabled_dimension_types
from ..envelope import BusinessError, envelope
from ..models.answer import Answer
from ..models.knowledge_base import KnowledgeBase
from ..models.knowledge_point import KnowledgePoint
from ..schemas.knowledge_point import (
    AnswerCreate,
    AnswerEdit,
    AnswerOut,
    KnowledgePointCreate,
    KnowledgePointDeleteRequest,
    KnowledgePointOut,
    KnowledgePointUpdate,
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


@router.get("")
def list_knowledge_points(
    kb_id: int,
    status: Literal["active", "deleted"] = Query(default="active"),
    db: Session = Depends(get_db),
) -> dict:
    _get_kb_or_404(db, kb_id)

    count_by_kp = dict(
        db.execute(
            select(Answer.knowledge_point_id, func.count())
            .where(Answer.knowledge_base_id == kb_id, Answer.revoked.is_(False))
            .group_by(Answer.knowledge_point_id)
        ).all()
    )

    rows = (
        db.execute(
            select(KnowledgePoint)
            .where(KnowledgePoint.knowledge_base_id == kb_id, KnowledgePoint.status == status)
            .order_by(KnowledgePoint.id)
        )
        .scalars()
        .all()
    )
    out = [_to_kp_out(kp, count_by_kp.get(kp.id, 0)) for kp in rows]
    return envelope([o.model_dump(mode="json") for o in out])


@router.get("/{kp_id}")
def get_knowledge_point(kb_id: int, kp_id: int, db: Session = Depends(get_db)) -> dict:
    kp = _get_kp_or_404(db, kb_id, kp_id)
    count = _get_active_answer_count(db, kp_id)
    return envelope(_to_kp_out(kp, count).model_dump(mode="json"))


@router.patch("/{kp_id}")
def update_knowledge_point(
    kb_id: int, kp_id: int, payload: KnowledgePointUpdate, db: Session = Depends(get_db)
) -> dict:
    kp = _get_kp_or_404(db, kb_id, kp_id)

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

    answer = Answer(
        knowledge_base_id=kb_id,
        knowledge_point_id=kp_id,
        coord=normalized,
        coord_hash=compute_coord_hash(normalized),
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
