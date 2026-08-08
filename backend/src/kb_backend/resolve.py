"""Shared resolution engine (docs/PRD.md §4.6.1) — the single implementation
behind both the list-filter endpoint and the single-point resolve endpoint
(issue #5). Ported from frontend-mock/assets/app.js's `resolveAnswer` /
`liveGroups` / `coordCompatible`, with PRD text (not just the JS) as the
source of truth for the created_at tie-breaks — see
docs/specs/2026-08-08-resolve-engine-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models.answer import Answer
from .models.dimension import DimensionDefinition

ResolveStatus = Literal["exact", "weighted", "default", "fallback-latest", "none"]


@dataclass(frozen=True)
class LiveGroup:
    coord: dict[str, Any]
    coord_hash: str
    live_answer: Answer
    spec: int
    weight: int


@dataclass(frozen=True)
class ResolveResult:
    status: ResolveStatus
    answer: Answer | None


@dataclass(frozen=True)
class AnswerGroupSummary:
    coord: dict[str, Any]
    coord_hash: str
    revoked: bool
    version_count: int
    latest_answer: Answer
    live_answer: Answer | None


def _dimension_weights(db: Session, keys: set[str]) -> dict[str, int]:
    if not keys:
        return {}
    rows = db.execute(
        select(DimensionDefinition.key, DimensionDefinition.weight).where(DimensionDefinition.key.in_(keys))
    ).all()
    return dict(rows)


def compute_live_groups(db: Session, kb_id: int, kp_id: int, at: date) -> list[LiveGroup]:
    """Step 1 of §4.6.1: group this knowledge point's non-revoked answers by
    coord_hash, and within each group pick the "current version" at time
    `at` — the row with the largest (effective_time, created_at), among
    rows with effective_time <= at. A group with no such row (every version
    is later than `at`) does not exist at this point in time and is
    dropped."""
    rows = (
        db.execute(
            select(Answer).where(
                Answer.knowledge_base_id == kb_id,
                Answer.knowledge_point_id == kp_id,
                Answer.revoked.is_(False),
                Answer.effective_time <= at,
            )
        )
        .scalars()
        .all()
    )

    by_hash: dict[str, list[Answer]] = {}
    for row in rows:
        by_hash.setdefault(row.coord_hash, []).append(row)

    all_keys: set[str] = set()
    for versions in by_hash.values():
        all_keys.update(versions[0].coord.keys())
    weights = _dimension_weights(db, all_keys)

    groups = []
    for coord_hash, versions in by_hash.items():
        # id as a final tie-break: `versions` comes from an unordered SELECT
        # (no ORDER BY), so relying on Python's stable max() over
        # MySQL's execution-plan-dependent row order would make the winner
        # non-deterministic whenever (effective_time, created_at) also tie.
        # Found by the Kimi review gate on PR #21.
        current = max(versions, key=lambda a: (a.effective_time, a.created_at, a.id))
        coord = current.coord
        groups.append(
            LiveGroup(
                coord=coord,
                coord_hash=coord_hash,
                live_answer=current,
                spec=len(coord),
                weight=sum(weights.get(k, 0) for k in coord),
            )
        )
    return groups


def compute_all_answer_groups(db: Session, kb_id: int, kp_id: int, at: date) -> list[AnswerGroupSummary]:
    """For the read-only answer-group tree (issue #7 §2) — deliberately
    separate from `compute_live_groups`, not a wrapper around it:
    `compute_live_groups` filters `revoked.is_(False)` at the SQL level, so
    a whole-chain-revoked coord group (e.g. from edit_answer's migration
    branch) never appears in its output at all. The tree view must show
    revoked chains too (struck through), per PRD §4.4's "全部答案的分组树"
    and frontend-mock's kpAnswerTree — so this queries every answer for the
    knowledge point, revoked or not, effective yet or not."""
    rows = (
        db.execute(
            select(Answer).where(
                Answer.knowledge_base_id == kb_id,
                Answer.knowledge_point_id == kp_id,
            )
        )
        .scalars()
        .all()
    )

    by_hash: dict[str, list[Answer]] = {}
    for row in rows:
        by_hash.setdefault(row.coord_hash, []).append(row)

    summaries = []
    for coord_hash, versions in by_hash.items():
        latest = max(versions, key=lambda a: (a.effective_time, a.created_at, a.id))
        # Revocation is a whole-chain property (PRD §6 rule #4) — every row
        # sharing a coord_hash carries the same `revoked` value, so the
        # latest version's flag speaks for the whole chain.
        live = next(
            (
                v
                for v in sorted(versions, key=lambda a: (a.effective_time, a.created_at, a.id), reverse=True)
                if not v.revoked and v.effective_time <= at
            ),
            None,
        )
        summaries.append(
            AnswerGroupSummary(
                coord=latest.coord,
                coord_hash=coord_hash,
                revoked=latest.revoked,
                version_count=len(versions),
                latest_answer=latest,
                live_answer=live,
            )
        )
    return sorted(summaries, key=lambda s: s.coord_hash)


def _coord_compatible(group_coord: dict[str, Any], query_coord: dict[str, Any]) -> bool:
    # Every key the GROUP specifies must agree with the query wherever the
    # query also specifies it; a key the query asks about but the group
    # never wrote is not checked (and vice versa). A coord={} group is
    # therefore always compatible — it has nothing to disagree on — which is
    # a deliberate, PRD/demo-sanctioned property, not an oversight: it lets
    # the default answer act as a low-priority (spec=0) fallback candidate
    # rather than being excluded outright.
    for key, value in group_coord.items():
        if key not in query_coord:
            continue
        if value != query_coord[key]:
            return False
    return True


def resolve(groups: list[LiveGroup], query_coord: dict[str, Any]) -> ResolveResult:
    """Step 2 of §4.6.1. `query_coord` must already be normalized (see
    coord.normalize_coord) so its values compare equal to the groups'
    already-normalized coord values."""
    if not groups:
        return ResolveResult(status="none", answer=None)

    if not query_coord:
        default_group = next((g for g in groups if g.spec == 0), None)
        if default_group is not None:
            return ResolveResult(status="default", answer=default_group.live_answer)
        latest = max(
            groups, key=lambda g: (g.live_answer.effective_time, g.live_answer.created_at, g.live_answer.id)
        )
        return ResolveResult(status="fallback-latest", answer=latest.live_answer)

    candidates = [g for g in groups if _coord_compatible(g.coord, query_coord)]
    if not candidates:
        return ResolveResult(status="none", answer=None)

    top = max(
        candidates,
        key=lambda g: (
            g.spec,
            g.weight,
            g.live_answer.effective_time,
            g.live_answer.created_at,
            g.live_answer.id,
        ),
    )
    is_exact = top.spec == len(query_coord) and all(
        top.coord[k] == query_coord.get(k) for k in top.coord
    )
    return ResolveResult(status="exact" if is_exact else "weighted", answer=top.live_answer)
