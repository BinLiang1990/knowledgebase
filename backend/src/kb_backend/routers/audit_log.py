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
        kp_title, kb_id, kb_name = kp_lookup[entry.knowledge_point_id]
        row = GlobalChangeLogEntryOut(
            **ChangeLogEntryOut.model_validate(entry).model_dump(),
            knowledge_base_id=kb_id,
            knowledge_base_name=kb_name,
            knowledge_point_title=kp_title,
        )
        out.append(row.model_dump(mode="json"))
    return envelope(out)
