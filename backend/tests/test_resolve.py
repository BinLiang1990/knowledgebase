from datetime import date, datetime

from kb_backend.models.answer import Answer
from kb_backend.resolve import LiveGroup, resolve


def _answer(effective_time: str, created_at: str, content: str = "content") -> Answer:
    return Answer(
        content=content,
        effective_time=date.fromisoformat(effective_time),
        created_at=datetime.fromisoformat(created_at),
    )


def _group(coord: dict, spec: int, weight: int, effective_time: str, created_at: str, content: str = "c") -> LiveGroup:
    return LiveGroup(
        coord=coord,
        coord_hash=f"hash-{coord}",
        live_answer=_answer(effective_time, created_at, content),
        spec=spec,
        weight=weight,
    )


def test_resolve_no_groups_returns_none_regardless_of_query() -> None:
    """Found by adversarial review during issue #5 design: this guard must
    run before the empty/non-empty query branch, not be folded into it."""
    assert resolve([], {}).status == "none"
    assert resolve([], {"tenant": "acme"}).status == "none"


def test_resolve_empty_query_returns_default_when_default_group_exists() -> None:
    default_group = _group({}, spec=0, weight=0, effective_time="2026-08-01", created_at="2026-08-01T00:00:00", content="default")
    other = _group({"tenant": "acme"}, spec=1, weight=90, effective_time="2026-08-05", created_at="2026-08-05T00:00:00")
    result = resolve([default_group, other], {})
    assert result.status == "default"
    assert result.answer.content == "default"


def test_resolve_empty_query_falls_back_to_latest_when_no_default_group() -> None:
    older = _group({"tenant": "acme"}, spec=1, weight=90, effective_time="2026-08-01", created_at="2026-08-01T00:00:00", content="older")
    newer = _group({"tenant": "other"}, spec=1, weight=90, effective_time="2026-08-05", created_at="2026-08-05T00:00:00", content="newer")
    result = resolve([older, newer], {})
    assert result.status == "fallback-latest"
    assert result.answer.content == "newer"


def test_resolve_exact_match() -> None:
    default_group = _group({}, spec=0, weight=0, effective_time="2026-08-01", created_at="2026-08-01T00:00:00", content="default")
    exact_group = _group({"tenant": "acme"}, spec=1, weight=90, effective_time="2026-08-05", created_at="2026-08-05T00:00:00", content="exact")
    result = resolve([default_group, exact_group], {"tenant": "acme"})
    assert result.status == "exact"
    assert result.answer.content == "exact"


def test_resolve_weighted_fallback_to_default_when_no_exact_match() -> None:
    """A query for a value that matches no specific group still resolves to
    the always-compatible coord={} default group, tagged 'weighted' (not
    'none') — a deliberate property of the algorithm, not a bug."""
    default_group = _group({}, spec=0, weight=0, effective_time="2026-08-01", created_at="2026-08-01T00:00:00", content="default")
    other_tenant = _group({"tenant": "acme"}, spec=1, weight=90, effective_time="2026-08-05", created_at="2026-08-05T00:00:00", content="acme-specific")
    result = resolve([default_group, other_tenant], {"tenant": "some-other-tenant"})
    assert result.status == "weighted"
    assert result.answer.content == "default"


def test_resolve_candidate_with_disjoint_coord_still_compatible_and_can_win() -> None:
    """A group whose coord shares zero keys with the query is still
    'compatible' by the literal algorithm (nothing to conflict on) — ranked
    by spec/weight/recency like any other candidate."""
    disjoint = _group({"priority": 5}, spec=1, weight=10, effective_time="2026-08-05", created_at="2026-08-05T00:00:00", content="disjoint")
    result = resolve([disjoint], {"tenant": "acme"})
    assert result.status == "weighted"
    assert result.answer.content == "disjoint"


def test_resolve_no_compatible_candidates_returns_none() -> None:
    conflicting = _group({"tenant": "acme"}, spec=1, weight=90, effective_time="2026-08-05", created_at="2026-08-05T00:00:00")
    result = resolve([conflicting], {"tenant": "other-tenant"})
    assert result.status == "none"


def test_resolve_ranks_by_spec_then_weight_then_effective_time_then_created_at() -> None:
    low_spec = _group({"tenant": "acme"}, spec=1, weight=90, effective_time="2026-08-05", created_at="2026-08-05T00:00:00", content="low-spec")
    high_spec = _group(
        {"tenant": "acme", "priority": 5}, spec=2, weight=100, effective_time="2026-08-01", created_at="2026-08-01T00:00:00", content="high-spec"
    )
    result = resolve([low_spec, high_spec], {"tenant": "acme", "priority": 5})
    assert result.answer.content == "high-spec"


def test_resolve_tie_break_uses_created_at_when_spec_weight_and_effective_time_all_equal() -> None:
    """This specific 4th-level tie-break is a new decision (not literally in
    the PRD or the demo, which only breaks ties via incidental JS Map
    insertion order) — see design doc §2.2 point 3. Locked in by this test."""
    first = _group({"tenant": "acme"}, spec=1, weight=90, effective_time="2026-08-05", created_at="2026-08-05T00:00:00", content="first")
    second = _group({"tenant": "other"}, spec=1, weight=90, effective_time="2026-08-05", created_at="2026-08-05T00:00:01", content="second")
    result = resolve([first, second], {})
    assert result.status == "fallback-latest"
    assert result.answer.content == "second"
