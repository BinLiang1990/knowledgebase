"""知识库分类树 (PRD §4.11, issue #39)。

树的规模预期在数百条以内（PRD §4.11 性能口径），所以：列表接口一次性
全量返回不分页；子孙集合、同级重排都是全量加载后内存计算，不做递归 SQL。
分类无留痕诉求，删除为物理删除；并发冲突不加锁（PRD §4.10），后到操作
按普通校验报错（分类不存在/重名），DB 的唯一索引与 RESTRICT 外键兜底。
"""

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..envelope import BusinessError, envelope
from ..models.knowledge_base import KnowledgeBase
from ..models.knowledge_base_category import KnowledgeBaseCategory
from ..schemas.category import CategoryCreate, CategoryMove, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["category"])

_NOT_FOUND_MSG = "分类不存在"
_DUPLICATE_NAME_MSG = "同一父分类下已存在同名分类"
_CYCLE_MSG = "不能移动到自己或自己的子孙分类下"
_MYSQL_ER_DUP_ENTRY = 1062


def _raise_if_duplicate_name(exc: IntegrityError) -> None:
    # 同 routers/knowledge_base.py 的同名函数：只把真正的 duplicate entry
    # 翻译成业务错误，其他完整性错误（如 RESTRICT 外键）原样抛出
    orig_args = getattr(exc.orig, "args", ())
    if orig_args and orig_args[0] == _MYSQL_ER_DUP_ENTRY:
        raise BusinessError(_DUPLICATE_NAME_MSG, status_code=400) from exc
    raise exc


def _get_or_404(db: Session, category_id: int) -> KnowledgeBaseCategory:
    category = db.get(KnowledgeBaseCategory, category_id)
    if category is None:
        raise BusinessError(_NOT_FOUND_MSG, status_code=404)
    return category


def _ensure_name_available(
    db: Session, name: str, parent_id: int | None, exclude_id: int | None = None
) -> None:
    # 应用级查重是主防线：MySQL 的唯一索引 (parent_id, name) 不约束
    # parent_id IS NULL 的行，顶级分类之间的重名只有这里能拦（model 注释）。
    # name 列与 knowledge_base.name 同为 utf8mb4_0900_ai_ci，比较天然
    # 大小写/重音不敏感，与知识库名称查重的既定口径一致。
    stmt = select(KnowledgeBaseCategory.id).where(KnowledgeBaseCategory.name == name)
    if parent_id is None:
        stmt = stmt.where(KnowledgeBaseCategory.parent_id.is_(None))
    else:
        stmt = stmt.where(KnowledgeBaseCategory.parent_id == parent_id)
    if exclude_id is not None:
        stmt = stmt.where(KnowledgeBaseCategory.id != exclude_id)
    if db.execute(stmt).first() is not None:
        raise BusinessError(_DUPLICATE_NAME_MSG, status_code=400)


def descendant_ids(db: Session, category_id: int) -> set[int]:
    """category_id 的全部子孙（不含自身）。全量加载 + 内存 BFS。

    供本路由（防成环、删除校验）与知识库列表的按分类过滤（含子孙语义，
    PRD §4.11）共用。"""
    rows = db.execute(
        select(KnowledgeBaseCategory.id, KnowledgeBaseCategory.parent_id)
    ).all()
    children_by_parent: dict[int | None, list[int]] = defaultdict(list)
    for cid, pid in rows:
        children_by_parent[pid].append(cid)

    out: set[int] = set()
    queue = list(children_by_parent.get(category_id, []))
    while queue:
        current = queue.pop()
        out.add(current)
        queue.extend(children_by_parent.get(current, []))
    return out


def _ensure_not_cycle(db: Session, category_id: int, new_parent_id: int | None) -> None:
    if new_parent_id is None:
        return
    if new_parent_id == category_id or new_parent_id in descendant_ids(db, category_id):
        raise BusinessError(_CYCLE_MSG, status_code=400)


def _siblings_ordered(
    db: Session, parent_id: int | None, exclude_id: int | None = None
) -> list[KnowledgeBaseCategory]:
    stmt = select(KnowledgeBaseCategory).order_by(
        KnowledgeBaseCategory.sort_order, KnowledgeBaseCategory.id
    )
    if parent_id is None:
        stmt = stmt.where(KnowledgeBaseCategory.parent_id.is_(None))
    else:
        stmt = stmt.where(KnowledgeBaseCategory.parent_id == parent_id)
    if exclude_id is not None:
        stmt = stmt.where(KnowledgeBaseCategory.id != exclude_id)
    return list(db.execute(stmt).scalars().all())


def _next_sort_order(db: Session, parent_id: int | None, exclude_id: int | None = None) -> int:
    siblings = _siblings_ordered(db, parent_id, exclude_id=exclude_id)
    if not siblings:
        return 0
    return siblings[-1].sort_order + 1


def _to_out(category: KnowledgeBaseCategory, active_kb_count: int) -> CategoryOut:
    return CategoryOut(
        id=category.id,
        parent_id=category.parent_id,
        name=category.name,
        sort_order=category.sort_order,
        active_knowledge_base_count=active_kb_count,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


def _single_out_envelope(db: Session, category: KnowledgeBaseCategory) -> dict:
    count = db.execute(
        select(func.count())
        .select_from(KnowledgeBase)
        .where(
            KnowledgeBase.category_id == category.id,
            KnowledgeBase.status == "active",
        )
    ).scalar_one()
    return envelope(_to_out(category, count).model_dump(mode="json"))


@router.get("")
def list_categories(db: Session = Depends(get_db)) -> dict:
    """全量扁平列表（不分页，PRD §4.11 性能口径），按 (parent_id 分组内的
    sort_order, id) 排序；树形组装与子树合计数由前端完成。每条附带直属的
    启用中知识库数——只统计 active（PRD §4.11 未决 #1 的建议口径）。"""
    count_by_category = dict(
        db.execute(
            select(KnowledgeBase.category_id, func.count())
            .where(
                KnowledgeBase.status == "active",
                KnowledgeBase.category_id.is_not(None),
            )
            .group_by(KnowledgeBase.category_id)
        ).all()
    )
    rows = (
        db.execute(
            select(KnowledgeBaseCategory).order_by(
                KnowledgeBaseCategory.sort_order, KnowledgeBaseCategory.id
            )
        )
        .scalars()
        .all()
    )
    out = [_to_out(c, count_by_category.get(c.id, 0)) for c in rows]
    return envelope([o.model_dump(mode="json") for o in out])


@router.post("")
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)) -> dict:
    if payload.parent_id is not None:
        _get_or_404(db, payload.parent_id)
    _ensure_name_available(db, payload.name, payload.parent_id)

    category = KnowledgeBaseCategory(
        parent_id=payload.parent_id,
        name=payload.name,
        # 默认排同级末尾（PRD §4.11）
        sort_order=_next_sort_order(db, payload.parent_id),
    )
    db.add(category)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_if_duplicate_name(exc)
    db.refresh(category)
    return _single_out_envelope(db, category)


@router.patch("/{category_id}")
def update_category(
    category_id: int, payload: CategoryUpdate, db: Session = Depends(get_db)
) -> dict:
    category = _get_or_404(db, category_id)
    fields_set = payload.model_fields_set

    # 先算目标父级（可能不变），名称查重要按“改完之后”的 (parent, name)
    # 组合来查——只改名、只移动、同时改两者共用同一条校验路径
    new_parent_id = category.parent_id
    if "parent_id" in fields_set:
        new_parent_id = payload.parent_id
        if new_parent_id is not None:
            _get_or_404(db, new_parent_id)
        _ensure_not_cycle(db, category_id, new_parent_id)
    new_name = payload.name if payload.name is not None else category.name

    parent_changed = new_parent_id != category.parent_id
    if parent_changed or new_name != category.name:
        _ensure_name_available(db, new_name, new_parent_id, exclude_id=category_id)

    category.name = new_name
    if parent_changed:
        category.parent_id = new_parent_id
        # 换父级 = 移动节点：排到新同级末尾（子树整体随迁——子节点的
        # parent_id 指向本节点，不需要动）
        category.sort_order = _next_sort_order(db, new_parent_id, exclude_id=category_id)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_if_duplicate_name(exc)
    db.refresh(category)
    return _single_out_envelope(db, category)


@router.delete("/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db)) -> dict:
    """仅允许删除空分类（PRD §4.11）：无子分类、且无知识库归属——知识库
    含已停用的（占用即阻塞），与前端删除弹窗的口径一致。错误信息带上
    两个数量，便于用户先行迁移。"""
    category = _get_or_404(db, category_id)

    child_count = db.execute(
        select(func.count())
        .select_from(KnowledgeBaseCategory)
        .where(KnowledgeBaseCategory.parent_id == category_id)
    ).scalar_one()
    kb_count = db.execute(
        select(func.count())
        .select_from(KnowledgeBase)
        .where(KnowledgeBase.category_id == category_id)
    ).scalar_one()
    if child_count or kb_count:
        raise BusinessError(
            f"无法删除：该分类下仍有 {child_count} 个子分类、{kb_count} 个知识库（含已停用），"
            "请先迁移或清空后再删",
            status_code=400,
        )

    db.delete(category)
    try:
        db.commit()
    except IntegrityError as exc:
        # 并发窗口内刚好有子分类/知识库挂进来：RESTRICT 外键会拒绝删除，
        # 翻译成与上面一致的业务错误而不是 500
        db.rollback()
        raise BusinessError(
            "无法删除：该分类下仍有子分类或知识库，请刷新后重试", status_code=400
        ) from exc
    return envelope()


@router.post("/{category_id}/move")
def move_category(
    category_id: int, payload: CategoryMove, db: Session = Depends(get_db)
) -> dict:
    """拖拽落点 (PRD §4.11)：before/after = 插入为目标的前/后同级，
    inside = 挂为目标的子分类、排子级末尾。校验失败整体不生效（单事务），
    不允许出现「父级改了但排序没改」的部分生效状态。"""
    dragged = _get_or_404(db, category_id)
    if payload.target_id == category_id:
        raise BusinessError(_CYCLE_MSG, status_code=400)
    target = _get_or_404(db, payload.target_id)
    if payload.target_id in descendant_ids(db, category_id):
        raise BusinessError(_CYCLE_MSG, status_code=400)

    new_parent_id = target.id if payload.position == "inside" else target.parent_id
    if new_parent_id != dragged.parent_id:
        _ensure_name_available(db, dragged.name, new_parent_id, exclude_id=category_id)

    dragged.parent_id = new_parent_id
    if payload.position == "inside":
        dragged.sort_order = _next_sort_order(db, new_parent_id, exclude_id=category_id)
    else:
        # 新同级序列（不含 dragged）里找到 target 的位置，把 dragged 插进去，
        # 然后整组按下标重排——sort_order 是数组下标语义，不留间隙
        siblings = _siblings_ordered(db, new_parent_id, exclude_id=category_id)
        target_index = next(i for i, c in enumerate(siblings) if c.id == target.id)
        insert_at = target_index if payload.position == "before" else target_index + 1
        siblings.insert(insert_at, dragged)
        for index, sibling in enumerate(siblings):
            sibling.sort_order = index

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_if_duplicate_name(exc)
    db.refresh(dragged)
    return _single_out_envelope(db, dragged)
