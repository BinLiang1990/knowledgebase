from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..change_log import build_change_log
from ..db import get_db
from ..envelope import envelope
from ..models.answer import Answer
from ..models.knowledge_base import KnowledgeBase
from ..models.knowledge_point import KnowledgePoint
from ..schemas.change_log import ChangeLogEntryOut, GlobalChangeLogEntryOut

router = APIRouter(tags=["audit-log"])


@router.get("/change-log")
def get_global_change_log(db: Session = Depends(get_db)) -> dict:
    """全局操作日志 (issue #12, design doc §4.4/§4.8) — the same per-answer
    write-order timeline as get_change_log, across every knowledge base,
    with knowledge_base_name/knowledge_point_title inlined (design doc
    §4.4 — the frontend can't reasonably pre-fetch every knowledge point's
    title just to render one log page, unlike the small, likely-already-
    fetched knowledge base list).

    Deliberately does NOT filter by knowledge_point.status or
    knowledge_base.status: this is an audit trail, and a since-deleted
    knowledge point's or deactivated knowledge base's history must remain
    visible — a different scope than get_knowledge_base_stats, which
    intentionally only counts *currently active* knowledge points (design
    doc §4.4 vs §4.5: the log answers "what happened", stats answers
    "what is true right now").

    Uses a LEFT JOIN for the enrichment lookup, not INNER — defensive
    against an orphaned Answer row, even though this schema's
    ondelete="RESTRICT" FK plus the absence of any physical-delete
    endpoint for KnowledgePoint/KnowledgeBase means that can't actually
    happen today.

    No pagination — deliberate, not an oversight (Kimi 终审 flagged the
    unbounded response on PR #28): every other list endpoint in this
    codebase (list_knowledge_points, list_dimensions, list_answer_groups)
    is equally unpaginated, and PRD §4.10 explicitly defers large-scale
    query performance work to P2, not blocking P0/P1 delivery. Introducing
    a pagination convention that exists nowhere else in this API, for one
    endpoint, ahead of any known frontend need for it, is scope beyond
    this issue — see design doc §4.6 for the full reasoning.
    """
    answers = db.execute(select(Answer)).scalars().all()
    entries = build_change_log(list(answers))

    lookup_rows = db.execute(
        select(KnowledgePoint.id, KnowledgePoint.title, KnowledgeBase.id, KnowledgeBase.name).outerjoin(
            KnowledgeBase, KnowledgePoint.knowledge_base_id == KnowledgeBase.id
        )
    ).all()
    kp_lookup = {kp_id: (title, kb_id, kb_name) for kp_id, title, kb_id, kb_name in lookup_rows}

    out = []
    for entry in entries:
        # .get(), not kp_lookup[...] — a bracket lookup would raise KeyError
        # on exactly the orphan case the LEFT JOIN above is meant to guard
        # against, defeating the whole point of choosing LEFT over INNER.
        # Skip a genuinely orphaned row rather than 500ing the entire
        # global log over one unreachable-in-practice row. Kimi 终审
        # finding on PR #28.
        lookup = kp_lookup.get(entry.knowledge_point_id)
        if lookup is None:
            continue
        kp_title, kb_id, kb_name = lookup
        row = GlobalChangeLogEntryOut(
            **ChangeLogEntryOut.model_validate(entry).model_dump(),
            knowledge_base_id=kb_id,
            knowledge_base_name=kb_name,
            knowledge_point_title=kp_title,
        )
        out.append(row.model_dump(mode="json"))
    return envelope(out)
