"""Change-log derivation (docs/PRD.md §4.7/§4.8, issue #12) — a pure,
read-only view over Answer history. Deliberately separate from
resolve.py's compute_all_answer_groups/compute_live_groups: those answer
"which version is current at time `at`" (sorted primarily by
effective_time); this answers "in what order did these writes happen"
(sorted purely by created_at). The two questions are independent — a
backfilled effective_time can sort earlier than other versions for
resolution purposes while still having been *written* later — so they
need their own algorithm rather than a shared, parameterized one. Ported
from frontend-mock/assets/app.js's changeLogRows, with one deliberate
correction (see ChangeLogEntry.status below) and one bug the JS original
didn't have to worry about (grouping key, see build_change_log).

docs/specs/2026-08-09-change-log-and-kb-stats-api-design.md §4.1/§4.2.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from .models.answer import Answer

ChangeLogAction = Literal["create", "edit", "revoke"]
ChangeLogStatus = Literal["live", "superseded", "revoked"]


@dataclass(frozen=True)
class ChangeLogEntry:
    time: datetime
    knowledge_point_id: int
    answer_id: int
    operator: str
    action: ChangeLogAction
    coord: dict[str, Any]
    before_content: str | None
    after_content: str | None
    source: str
    revoke_reason: str | None
    status: ChangeLogStatus
    revocable: bool


def build_change_log(answers: list[Answer]) -> list[ChangeLogEntry]:
    """Group by (knowledge_point_id, coord_hash) — NOT coord_hash alone.
    compute_coord_hash is a pure function of the normalized coord dict, with
    zero knowledge-point awareness (coord.py) — coord_hash collides across
    every knowledge point that happens to share a coord, guaranteed for the
    default answer (coord={}). Grouping by coord_hash alone (as
    resolve.py's helpers effectively do) is only safe there because their
    caller has already filtered the input to a single knowledge_point_id
    first. This function's caller for the global log has NOT done that
    filtering — two unrelated knowledge points' version chains would get
    spliced into one, with before_content leaking from one knowledge point
    into another's row. Caught by adversarial review before this was
    implemented.
    """
    by_chain: dict[tuple[int, str], list[Answer]] = {}
    for a in answers:
        by_chain.setdefault((a.knowledge_point_id, a.coord_hash), []).append(a)

    entries: list[ChangeLogEntry] = []
    for chain in by_chain.values():
        # id tie-break: created_at is DATETIME(6) (microsecond precision) —
        # still theoretically collidable, and unlike resolve.py's own
        # max()-over-unordered-rows this is an explicit sort, so the same
        # defensive tie-break applies.
        chain.sort(key=lambda a: (a.created_at, a.id))
        for i, a in enumerate(chain):
            is_last = i == len(chain) - 1
            # Status only looks at `revoked` on the LAST version. A
            # whole-chain revoke (edit_answer's migration branch, or the
            # dedicated revoke endpoint) sets revoked=True on every row in
            # the chain, not just the last one — but a version that was
            # already superseded by a later write stays "superseded"
            # regardless of that later batch UPDATE; only the chain's
            # current (last) version transitions to "revoked". Matches
            # frontend-mock's changeLogRows (app.js) exactly.
            if not is_last:
                status: ChangeLogStatus = "superseded"
            else:
                status = "revoked" if a.revoked else "live"
            entries.append(
                ChangeLogEntry(
                    time=a.created_at,
                    knowledge_point_id=a.knowledge_point_id,
                    answer_id=a.id,
                    operator=a.operator,
                    action="create" if i == 0 else "edit",
                    coord=a.coord,
                    before_content=None if i == 0 else chain[i - 1].content,
                    after_content=a.content,
                    source=a.source,
                    revoke_reason=None,
                    status=status,
                    revocable=is_last and not a.revoked,
                )
            )
        last = chain[-1]
        if last.revoked:
            # Synthetic entry for the revoke action itself, distinct from
            # the last version's own row above. Deliberately status="revoked"
            # here (not demo's "生效"/"live") — this row describes the fact
            # that the chain was just revoked, so labeling it "live" would
            # be self-contradictory; see design doc §4.2 for why this one
            # deviation from the demo is correct, not a missed port.
            entries.append(
                ChangeLogEntry(
                    time=last.revoked_at or last.created_at,
                    knowledge_point_id=last.knowledge_point_id,
                    answer_id=last.id,
                    operator=last.revoked_by or "admin",
                    action="revoke",
                    coord=last.coord,
                    before_content=last.content,
                    after_content=None,
                    source=last.source,
                    revoke_reason=last.revoke_reason,
                    status="revoked",
                    revocable=False,
                )
            )

    entries.sort(key=lambda e: (e.time, e.answer_id), reverse=True)
    return entries
