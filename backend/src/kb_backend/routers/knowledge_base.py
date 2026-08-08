from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..envelope import BusinessError, envelope
from ..models.dimension import DimensionDefinition, KnowledgeBaseEnabledDimension
from ..models.knowledge_base import KnowledgeBase
from ..models.knowledge_point import KnowledgePoint
from ..schemas.dimension import DimensionOut, EnabledDimensionsUpdate
from ..schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseOut, KnowledgeBaseUpdate

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-base"])

_DUPLICATE_NAME_MSG = "知识库名称已存在，请使用其他名称"
_NOT_FOUND_MSG = "知识库不存在"
_MYSQL_ER_DUP_ENTRY = 1062


def _raise_if_duplicate_name(exc: IntegrityError) -> None:
    # Only translate an actual "duplicate entry" violation into the clean
    # business error; any other integrity error (e.g. a future constraint
    # added to this table) re-raises as-is instead of being misreported as a
    # duplicate name. Found by the Kimi review gate on PR #18.
    orig_args = getattr(exc.orig, "args", ())
    if orig_args and orig_args[0] == _MYSQL_ER_DUP_ENTRY:
        raise BusinessError(_DUPLICATE_NAME_MSG, status_code=400) from exc
    raise exc


def _get_active_point_count(db: Session, knowledge_base_id: int) -> int:
    return (
        db.execute(
            select(func.count())
            .select_from(KnowledgePoint)
            .where(
                KnowledgePoint.knowledge_base_id == knowledge_base_id,
                KnowledgePoint.status == "active",
            )
        ).scalar_one()
    )


def _to_out(kb: KnowledgeBase, active_point_count: int) -> KnowledgeBaseOut:
    return KnowledgeBaseOut(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        status=kb.status,
        active_knowledge_point_count=active_point_count,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


def _get_or_404(db: Session, kb_id: int) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise BusinessError(_NOT_FOUND_MSG, status_code=404)
    return kb


def _ensure_name_available(db: Session, name: str, exclude_id: int | None = None) -> None:
    # `knowledge_base.name` uses utf8mb4_0900_ai_ci (issue #1), so this
    # comparison — and the backing unique index — are already case- and
    # accent-insensitive ("FAQ" collides with "faq"). That is treated as the
    # intended reading of PRD §4.1's "完全重复": it prevents confusing
    # near-duplicates, and changing it would mean altering an already-shipped
    # column collation. Flagged by the Codex outer-gate review on PR #18.
    stmt = select(KnowledgeBase.id).where(KnowledgeBase.name == name)
    if exclude_id is not None:
        stmt = stmt.where(KnowledgeBase.id != exclude_id)
    if db.execute(stmt).first() is not None:
        raise BusinessError(_DUPLICATE_NAME_MSG, status_code=400)


@router.post("")
def create_knowledge_base(payload: KnowledgeBaseCreate, db: Session = Depends(get_db)) -> dict:
    _ensure_name_available(db, payload.name)

    kb = KnowledgeBase(name=payload.name, description=payload.description, status="active")
    db.add(kb)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_if_duplicate_name(exc)
    db.refresh(kb)

    out = _to_out(kb, active_point_count=0)
    return envelope(out.model_dump(mode="json"))


@router.get("")
def list_knowledge_bases(
    status: Literal["active", "deprecated"] | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    count_by_kb = dict(
        db.execute(
            select(KnowledgePoint.knowledge_base_id, func.count())
            .where(KnowledgePoint.status == "active")
            .group_by(KnowledgePoint.knowledge_base_id)
        ).all()
    )

    stmt = select(KnowledgeBase).order_by(KnowledgeBase.id)
    if status is not None:
        stmt = stmt.where(KnowledgeBase.status == status)

    rows = db.execute(stmt).scalars().all()
    out = [_to_out(kb, count_by_kb.get(kb.id, 0)) for kb in rows]
    return envelope([o.model_dump(mode="json") for o in out])


@router.patch("/{kb_id}")
def update_knowledge_base(
    kb_id: int, payload: KnowledgeBaseUpdate, db: Session = Depends(get_db)
) -> dict:
    kb = _get_or_404(db, kb_id)

    fields_set = payload.model_fields_set
    if payload.name is not None and payload.name != kb.name:
        _ensure_name_available(db, payload.name, exclude_id=kb_id)
        kb.name = payload.name
    # `description` must distinguish "field omitted" (no change) from
    # "field explicitly sent as null" (clear it) — payload.description is
    # None in both cases, so check model_fields_set instead of the value.
    # Found by the Codex outer-gate review on PR #18.
    if "description" in fields_set:
        kb.description = payload.description

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_if_duplicate_name(exc)
    db.refresh(kb)

    out = _to_out(kb, _get_active_point_count(db, kb_id))
    return envelope(out.model_dump(mode="json"))


def _set_status(db: Session, kb_id: int, target_status: Literal["active", "deprecated"]) -> dict:
    kb = _get_or_404(db, kb_id)
    if kb.status != target_status:
        kb.status = target_status
        db.commit()
        db.refresh(kb)

    out = _to_out(kb, _get_active_point_count(db, kb_id))
    return envelope(out.model_dump(mode="json"))


@router.post("/{kb_id}/activate")
def activate_knowledge_base(kb_id: int, db: Session = Depends(get_db)) -> dict:
    return _set_status(db, kb_id, "active")


@router.post("/{kb_id}/deactivate")
def deactivate_knowledge_base(kb_id: int, db: Session = Depends(get_db)) -> dict:
    return _set_status(db, kb_id, "deprecated")


def _enabled_dimensions(db: Session, kb_id: int) -> list[DimensionDefinition]:
    # INNER JOIN (not outerjoin): a dimension that has been globally
    # deprecated must disappear from every KB's enabled list even though the
    # join-table row still exists (PRD §4.3). An outer join would let the
    # deprecated dimension's row survive with nulled-out columns instead of
    # being excluded.
    return (
        db.execute(
            select(DimensionDefinition)
            .join(
                KnowledgeBaseEnabledDimension,
                KnowledgeBaseEnabledDimension.dimension_key == DimensionDefinition.key,
            )
            .where(
                KnowledgeBaseEnabledDimension.knowledge_base_id == kb_id,
                DimensionDefinition.status == "active",
            )
            .order_by(DimensionDefinition.key)
        )
        .scalars()
        .all()
    )


def _enabled_dimensions_envelope(db: Session, kb_id: int) -> dict:
    rows = _enabled_dimensions(db, kb_id)
    out = [DimensionOut.model_validate(row) for row in rows]
    return envelope([o.model_dump(mode="json") for o in out])


@router.get("/{kb_id}/enabled-dimensions")
def list_enabled_dimensions(kb_id: int, db: Session = Depends(get_db)) -> dict:
    # A knowledge base's own active/deprecated status does not gate this
    # endpoint — read-only, no PRD text explicitly blocks it for a
    # deactivated KB. See design doc §3.3 for the reasoning; this is a
    # judgment call pending product confirmation, locked in by a test.
    _get_or_404(db, kb_id)
    return _enabled_dimensions_envelope(db, kb_id)


@router.put("/{kb_id}/enabled-dimensions")
def set_enabled_dimensions(
    kb_id: int, payload: EnabledDimensionsUpdate, db: Session = Depends(get_db)
) -> dict:
    """Whole-set replacement, not incremental toggle — mirrors the demo's
    checkbox-list-plus-one-save-button interaction (design doc §3.2)."""
    _get_or_404(db, kb_id)

    # Resolve each requested spelling to its canonical stored `key` via a
    # collation-aware equality lookup (dimension_definition.key uses the
    # same case/accent-insensitive utf8mb4_0900_ai_ci as knowledge_base.name)
    # before validating/deduping/inserting. A single batched `IN (...)`
    # lookup can't tell which requested spelling matched which returned row
    # once two requested values collapse onto the same DB row under that
    # collation (e.g. "Region" and "region"), so an exact-string Python
    # membership check against it would wrongly report an existing
    # dimension as "不存在". Resolving one at a time also makes dedup
    # canonical-key-based, not raw-spelling-based, and guarantees every
    # inserted row uses the DB's own spelling rather than whatever
    # case/accent variant the client happened to type. Codex outer-gate
    # finding on PR #25.
    keys: list[str] = []
    seen: set[str] = set()
    for requested_key in payload.dimension_keys:
        dim = db.execute(select(DimensionDefinition).where(DimensionDefinition.key == requested_key)).scalar_one_or_none()
        if dim is None:
            raise BusinessError(f"维度「{requested_key}」不存在", status_code=400)
        if dim.status != "active":
            raise BusinessError(f"维度「{requested_key}」已停用，无法启用", status_code=400)
        if dim.key not in seen:
            seen.add(dim.key)
            keys.append(dim.key)

    # Only replace the *active*-dimension portion of this KB's enabled set,
    # not the whole table. A dimension that was enabled here and later
    # globally deprecated keeps its join-table row on purpose (PRD §4.3 —
    # global deactivation doesn't touch KB-level links) but disappears from
    # _enabled_dimensions()'s INNER JOIN + status=active filter, so the
    # admin settings UI this endpoint backs can never show it as a
    # checkbox, let alone let the admin resubmit it. Deleting every row
    # unconditionally would silently erase that retained link the moment
    # anyone saves this KB's settings — reactivating the dimension later
    # would then no longer show it enabled for this KB. Codex outer-gate
    # finding on PR #25.
    #
    # A dimension can be deactivated by a concurrent request between the
    # validation loop above and this commit — Kimi 终审 finding on PR #25.
    # PRD §4.10 explicitly defers concurrency/conflict control to P2 and
    # this app takes no row locks anywhere else, so this doesn't add
    # `.with_for_update()` locking here either; instead this just makes
    # sure that race can never surface as an unhandled 500. Two outcomes:
    # (a) the dimension had no existing link for this KB — the insert
    # below creates one to a now-deprecated dimension, which is harmless
    # because _enabled_dimensions()/get_enabled_dimension_types() both
    # INNER JOIN on status=active, so that link is functionally inert
    # until someone reactivates the dimension (identical reasoning to why
    # "enabling a deprecated dimension" is accepted as harmless elsewhere
    # in this design); (b) the dimension already had a link — the delete
    # above skips it (no longer status=active) and the insert then hits
    # that same composite primary key, which IntegrityError below turns
    # into a clean retry-able error instead of a crash.
    try:
        db.execute(
            delete(KnowledgeBaseEnabledDimension).where(
                KnowledgeBaseEnabledDimension.knowledge_base_id == kb_id,
                KnowledgeBaseEnabledDimension.dimension_key.in_(
                    select(DimensionDefinition.key).where(DimensionDefinition.status == "active")
                ),
            )
        )
        for key in keys:
            db.add(KnowledgeBaseEnabledDimension(knowledge_base_id=kb_id, dimension_key=key))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError("启用维度失败，请刷新后重试", status_code=400) from exc

    return _enabled_dimensions_envelope(db, kb_id)
