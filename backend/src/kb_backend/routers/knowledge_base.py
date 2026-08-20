from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..dimensions import get_enabled_dimension_types
from ..envelope import BusinessError, envelope
from ..models.answer import Answer
from ..models.dimension import DimensionDefinition, KnowledgeBaseEnabledDimension
from ..models.knowledge_base import KnowledgeBase
from ..models.knowledge_base_category import KnowledgeBaseCategory
from ..models.knowledge_point import KnowledgePoint
from ..schemas.dimension import DimensionOut, EnabledDimensionsUpdate
from .category import descendant_ids
from ..schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBaseStatsOut,
    KnowledgeBaseUpdate,
)

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


def _to_out(
    kb: KnowledgeBase, active_point_count: int, category_name: str | None = None
) -> KnowledgeBaseOut:
    return KnowledgeBaseOut(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        status=kb.status,
        active_knowledge_point_count=active_point_count,
        category_id=kb.category_id,
        category_name=category_name,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


def _category_or_404(db: Session, category_id: int) -> KnowledgeBaseCategory:
    """写知识库/按分类过滤时的 category_id 存在性校验（PRD §4.11：报错
    拒绝，不做静默忽略/静默空列表）。"""
    category = db.get(KnowledgeBaseCategory, category_id)
    if category is None:
        raise BusinessError("分类不存在", status_code=404)
    return category


def _category_name(db: Session, category_id: int | None) -> str | None:
    if category_id is None:
        return None
    category = db.get(KnowledgeBaseCategory, category_id)
    return category.name if category is not None else None


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


def _resolve_dimension_keys(db: Session, requested_keys: list[str]) -> list[str]:
    """把请求里的维度 key 逐个解析成 DB 的规范拼写：存在性/启用状态校验 +
    按规范 key 去重。逐个查询而非批量 IN 的原因见 set_enabled_dimensions
    原注释（collation 折叠问题，Codex PR #25）——本函数就是从那里提取的，
    供「创建知识库时直接启用维度」复用。"""
    keys: list[str] = []
    seen: set[str] = set()
    for requested_key in requested_keys:
        dim = db.execute(
            select(DimensionDefinition).where(DimensionDefinition.key == requested_key)
        ).scalar_one_or_none()
        if dim is None:
            raise BusinessError(f"维度「{requested_key}」不存在", status_code=400)
        if dim.status != "active":
            raise BusinessError(f"维度「{requested_key}」已停用，无法启用", status_code=400)
        if dim.key not in seen:
            seen.add(dim.key)
            keys.append(dim.key)
    return keys


@router.post("")
def create_knowledge_base(payload: KnowledgeBaseCreate, db: Session = Depends(get_db)) -> dict:
    _ensure_name_available(db, payload.name)
    # 维度/分类校验都放在建库之前：任何一个不合法都不应留下半成品知识库
    keys = _resolve_dimension_keys(db, payload.enabled_dimension_keys or [])
    category_name: str | None = None
    if payload.category_id is not None:
        category_name = _category_or_404(db, payload.category_id).name

    kb = KnowledgeBase(
        name=payload.name,
        description=payload.description,
        status="active",
        category_id=payload.category_id,
    )
    db.add(kb)
    try:
        # 建库 + 启用维度同一事务（本功能的意义所在：不再需要建完后
        # 二段式地去「知识库设置」勾选）
        db.flush()
        for key in keys:
            db.add(KnowledgeBaseEnabledDimension(knowledge_base_id=kb.id, dimension_key=key))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_if_duplicate_name(exc)
    db.refresh(kb)

    out = _to_out(kb, active_point_count=0, category_name=category_name)
    return envelope(out.model_dump(mode="json"))


@router.get("")
def list_knowledge_bases(
    status: Literal["active", "deprecated"] | None = Query(default=None),
    category_id: int | None = Query(default=None),
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
    if category_id is not None:
        # PRD §4.11：过滤语义固定为「该分类及其全部子孙」，不提供仅直属
        # 开关；不存在的分类 id 报错而不是静默空列表。对外与界面同参数。
        _category_or_404(db, category_id)
        scope_ids = {category_id, *descendant_ids(db, category_id)}
        stmt = stmt.where(KnowledgeBase.category_id.in_(scope_ids))

    name_by_category = dict(
        db.execute(select(KnowledgeBaseCategory.id, KnowledgeBaseCategory.name)).all()
    )
    rows = db.execute(stmt).scalars().all()
    out = [
        _to_out(kb, count_by_kb.get(kb.id, 0), name_by_category.get(kb.category_id))
        for kb in rows
    ]
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
    # 同上：category_id 也要区分「未传(不改)」与「显式 null(置为未分类)」
    if "category_id" in fields_set:
        if payload.category_id is not None:
            _category_or_404(db, payload.category_id)
        kb.category_id = payload.category_id

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_if_duplicate_name(exc)
    db.refresh(kb)

    out = _to_out(kb, _get_active_point_count(db, kb_id), _category_name(db, kb.category_id))
    return envelope(out.model_dump(mode="json"))


def _set_status(db: Session, kb_id: int, target_status: Literal["active", "deprecated"]) -> dict:
    kb = _get_or_404(db, kb_id)
    if kb.status != target_status:
        kb.status = target_status
        db.commit()
        db.refresh(kb)

    out = _to_out(kb, _get_active_point_count(db, kb_id), _category_name(db, kb.category_id))
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
    # finding on PR #25. (逻辑提取为 _resolve_dimension_keys，与
    # create_knowledge_base 的"创建时启用维度"共用。)
    keys = _resolve_dimension_keys(db, payload.dimension_keys)

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


@router.get("/{kb_id}/dimension-values")
def list_dimension_values(
    kb_id: int,
    dimension_key: str = Query(min_length=1, max_length=100),
    db: Session = Depends(get_db),
) -> dict:
    """条件筛选下拉的候选取值：`dimension_key` 在本库现存答案条件里出现过的
    全部取值，去重后按字面排序。「现存」= 未撤回且知识点未删——与查询路径
    resolve 的可命中范围一致；详情页答案树虽然会展示已撤回分组，但候选只是
    输入辅助，手动输入仍然畅通，不为它扩大口径。

    dimension_key 走 query 参数而不进 path——维度 key 是管理员输入的任意
    文本（"?"/"#" 都合法），进 path 需要调用方逐处 encodeURIComponent
    （updateDimension 的教训，Codex PR #29）。取值在 Python 侧遍历 coord
    收集，不拼 JSON path 表达式（同 list_dimensions_admin 的理由，设计文档
    §4.4：key 里的 '.'/'"'/'$' 对 path 语法全都有含义）。"""
    _get_or_404(db, kb_id)

    # 与 _resolve_dimension_keys 同理的 collation 解析：先把请求拼写解析成
    # DB 规范 key（utf8mb4_0900_ai_ci 大小写/重音不敏感），再校验启用状态——
    # coord 里存的永远是规范拼写，用原始拼写直接查会静默漏配。
    dim = db.execute(
        select(DimensionDefinition).where(DimensionDefinition.key == dimension_key)
    ).scalar_one_or_none()
    if dim is None or dim.key not in get_enabled_dimension_types(db, kb_id):
        raise BusinessError(f"维度 {dimension_key} 未在本知识库启用", status_code=400)

    coords = (
        db.execute(
            select(Answer.coord)
            .join(KnowledgePoint, Answer.knowledge_point_id == KnowledgePoint.id)
            .where(
                Answer.knowledge_base_id == kb_id,
                Answer.revoked.is_(False),
                KnowledgePoint.status == "active",
            )
        )
        .scalars()
        .all()
    )
    values = {coord[dim.key] for coord in coords if dim.key in coord}
    # field_type 不可变（DimensionUpdate 没有该字段），同一 key 的取值类型
    # 同构；str.lower 排序对 text 是自然序，对其他类型也不至于抛 TypeError。
    return envelope(sorted(values, key=lambda v: (str(v).lower(), str(v))))


@router.get("/{kb_id}/stats")
def get_knowledge_base_stats(kb_id: int, db: Session = Depends(get_db)) -> dict:
    """知识库统计卡 (issue #12, design doc §4.5) — matches frontend-mock's
    computeKbStats exactly: subject_count/active_answer_count/
    today_change_count are all scoped to knowledge points that are
    currently active (status == "active"). A soft-deleted knowledge
    point's un-revoked answers do not count as "在用" even though
    Answer.revoked is still False on them — the KP's own deleted status is
    what excludes them, not anything on the Answer row itself. This is a
    deliberately different scope from get_change_log/the global /change-log
    endpoint, which show history regardless of KP/KB status (design doc
    §4.4) — stats answer "what is true right now", the log answers "what
    happened", and a knowledge point being deleted changes the first
    answer without erasing the second."""
    _get_or_404(db, kb_id)

    subject_count = _get_active_point_count(db, kb_id)

    active_answer_count = db.execute(
        select(func.count())
        .select_from(Answer)
        .join(KnowledgePoint, Answer.knowledge_point_id == KnowledgePoint.id)
        .where(
            Answer.knowledge_base_id == kb_id,
            Answer.revoked.is_(False),
            KnowledgePoint.status == "active",
        )
    ).scalar_one()

    enabled_dimension_count = len(get_enabled_dimension_types(db, kb_id))

    # Range comparison (>= today, < tomorrow), not DATE(created_at) — the
    # latter can't use an index on created_at even if one existed later,
    # and there's no reason to foreclose that option now. v1 assumes the
    # app server and the database server share the same timezone (no
    # explicit conversion is done anywhere else in this codebase either);
    # if they diverge in a real deployment, "today" could be off by the
    # difference near midnight — a known, accepted residual risk (design
    # doc §4.5), not something this endpoint tries to solve.
    today = date.today()
    tomorrow = today + timedelta(days=1)
    today_change_count = db.execute(
        select(func.count())
        .select_from(Answer)
        .join(KnowledgePoint, Answer.knowledge_point_id == KnowledgePoint.id)
        .where(
            Answer.knowledge_base_id == kb_id,
            KnowledgePoint.status == "active",
            (
                ((Answer.created_at >= today) & (Answer.created_at < tomorrow))
                | ((Answer.revoked_at >= today) & (Answer.revoked_at < tomorrow))
            ),
        )
    ).scalar_one()

    out = KnowledgeBaseStatsOut(
        subject_count=subject_count,
        active_answer_count=active_answer_count,
        enabled_dimension_count=enabled_dimension_count,
        today_change_count=today_change_count,
    )
    return envelope(out.model_dump(mode="json"))
