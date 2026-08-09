from datetime import datetime

from kb_backend.change_log import build_change_log
from kb_backend.coord import compute_coord_hash
from kb_backend.models.answer import Answer


def _answer(
    id: int,
    kp_id: int,
    created_at: datetime,
    coord: dict | None = None,
    content: str = "content",
    revoked: bool = False,
    revoked_at: datetime | None = None,
    revoked_by: str | None = None,
    revoke_reason: str | None = None,
    operator: str = "admin",
    source: str = "人工填报",
) -> Answer:
    coord = coord or {}
    return Answer(
        id=id,
        knowledge_base_id=1,
        knowledge_point_id=kp_id,
        coord=coord,
        coord_hash=compute_coord_hash(coord),
        content=content,
        effective_time=created_at.date(),
        operator=operator,
        source=source,
        note=None,
        revoked=revoked,
        revoked_at=revoked_at,
        revoked_by=revoked_by,
        revoke_reason=revoke_reason,
        created_at=created_at,
    )


def test_single_unrevoked_version_is_a_live_create_row() -> None:
    a = _answer(1, kp_id=10, created_at=datetime(2026, 8, 1, 10, 0, 0))
    entries = build_change_log([a])

    assert len(entries) == 1
    e = entries[0]
    assert e.action == "create"
    assert e.status == "live"
    assert e.revocable is True
    assert e.before_content is None
    assert e.after_content == "content"
    assert e.answer_id == 1


def test_edited_same_coord_appends_a_second_row_with_before_content() -> None:
    v1 = _answer(1, kp_id=10, created_at=datetime(2026, 8, 1, 10, 0, 0), content="v1")
    v2 = _answer(2, kp_id=10, created_at=datetime(2026, 8, 2, 10, 0, 0), content="v2")
    entries = build_change_log([v2, v1])  # order of input list must not matter

    entries_by_time = sorted(entries, key=lambda e: e.time)
    row1, row2 = entries_by_time

    assert row1.action == "create"
    assert row1.status == "superseded"
    assert row1.revocable is False

    assert row2.action == "edit"
    assert row2.status == "live"
    assert row2.revocable is True
    assert row2.before_content == "v1"
    assert row2.after_content == "v2"


def test_revoked_chain_gets_a_synthetic_revoke_row() -> None:
    a = _answer(
        1,
        kp_id=10,
        created_at=datetime(2026, 8, 1, 10, 0, 0),
        content="only version",
        revoked=True,
        revoked_at=datetime(2026, 8, 5, 9, 0, 0),
        revoked_by="admin",
        revoke_reason="写错了",
    )
    entries = build_change_log([a])

    assert len(entries) == 2
    version_row = next(e for e in entries if e.action == "create")
    revoke_row = next(e for e in entries if e.action == "revoke")

    assert version_row.status == "revoked"
    assert version_row.revocable is False

    assert revoke_row.status == "revoked"
    assert revoke_row.answer_id == 1
    assert revoke_row.before_content == "only version"
    assert revoke_row.after_content is None
    assert revoke_row.revoke_reason == "写错了"
    assert revoke_row.operator == "admin"
    assert revoke_row.time == datetime(2026, 8, 5, 9, 0, 0)
    assert revoke_row.revocable is False


def test_whole_chain_revoke_does_not_mark_non_last_versions_as_revoked() -> None:
    """Regression for the adversarial-review finding: edit_answer's
    migration branch / the dedicated revoke endpoint set revoked=True on
    EVERY row in a chain, not just the last one. Only the last
    (chronologically) version's row should show status="revoked" — earlier
    versions stay "superseded", exactly as frontend-mock's changeLogRows
    computes it (it never looks at `revoked` except on the last row)."""
    reason = "整条链撤回"
    v1 = _answer(
        1, kp_id=10, created_at=datetime(2026, 8, 1, 10, 0, 0), content="v1",
        revoked=True, revoked_at=datetime(2026, 8, 5, 9, 0, 0), revoked_by="admin", revoke_reason=reason,
    )
    v2 = _answer(
        2, kp_id=10, created_at=datetime(2026, 8, 2, 10, 0, 0), content="v2",
        revoked=True, revoked_at=datetime(2026, 8, 5, 9, 0, 0), revoked_by="admin", revoke_reason=reason,
    )
    v3 = _answer(
        3, kp_id=10, created_at=datetime(2026, 8, 3, 10, 0, 0), content="v3",
        revoked=True, revoked_at=datetime(2026, 8, 5, 9, 0, 0), revoked_by="admin", revoke_reason=reason,
    )
    entries = build_change_log([v1, v2, v3])

    version_rows = sorted((e for e in entries if e.action in ("create", "edit")), key=lambda e: e.time)
    assert [r.status for r in version_rows] == ["superseded", "superseded", "revoked"]
    assert [r.revocable for r in version_rows] == [False, False, False]

    revoke_rows = [e for e in entries if e.action == "revoke"]
    assert len(revoke_rows) == 1
    assert revoke_rows[0].answer_id == 3


def test_two_knowledge_points_sharing_a_coord_hash_do_not_get_spliced_together() -> None:
    """Regression for adversarial-review finding F0: grouping must be keyed
    by (knowledge_point_id, coord_hash), not coord_hash alone —
    compute_coord_hash is knowledge-point-agnostic, and two different KPs'
    default answers (coord={}) are guaranteed to collide on coord_hash."""
    kp_a_answer = _answer(1, kp_id=100, created_at=datetime(2026, 8, 1, 10, 0, 0), content="kp-a content", coord={})
    kp_b_answer = _answer(2, kp_id=200, created_at=datetime(2026, 8, 2, 10, 0, 0), content="kp-b content", coord={})
    assert kp_a_answer.coord_hash == kp_b_answer.coord_hash  # same coord => guaranteed hash collision

    entries = build_change_log([kp_a_answer, kp_b_answer])

    assert len(entries) == 2
    row_a = next(e for e in entries if e.knowledge_point_id == 100)
    row_b = next(e for e in entries if e.knowledge_point_id == 200)

    # Both must be their own chain's FIRST version ("create"), not one
    # mistaken for an edit of the other's chain, and before_content must
    # never leak from one knowledge point into the other's row.
    assert row_a.action == "create"
    assert row_a.before_content is None
    assert row_a.after_content == "kp-a content"

    assert row_b.action == "create"
    assert row_b.before_content is None
    assert row_b.after_content == "kp-b content"


def test_entries_across_chains_are_sorted_by_time_descending() -> None:
    older = _answer(1, kp_id=10, created_at=datetime(2026, 8, 1, 10, 0, 0), coord={"tenant": "a"})
    newer = _answer(2, kp_id=10, created_at=datetime(2026, 8, 5, 10, 0, 0), coord={"tenant": "b"})
    entries = build_change_log([older, newer])

    assert [e.answer_id for e in entries] == [2, 1]


def test_identical_created_at_ties_broken_by_answer_id_deterministically() -> None:
    same_time = datetime(2026, 8, 1, 10, 0, 0)
    a1 = _answer(5, kp_id=10, created_at=same_time, coord={"tenant": "a"})
    a2 = _answer(9, kp_id=10, created_at=same_time, coord={"tenant": "b"})

    entries_1 = build_change_log([a1, a2])
    entries_2 = build_change_log([a2, a1])

    assert [e.answer_id for e in entries_1] == [e.answer_id for e in entries_2]
