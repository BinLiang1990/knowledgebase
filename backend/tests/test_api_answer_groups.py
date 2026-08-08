"""Tests for GET .../knowledge-points/{id}/answer-groups (issue #7) — the
read-only, all-conditions view backing the frontend's expandable answer
tree. Deliberately exercises the revoked-chain case that compute_live_groups
alone would hide — see docs/specs/2026-08-08-kp-list-filter-ui-design.md §2.
"""
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _create_kb(client: TestClient, name: str) -> dict:
    return client.post("/knowledge-bases", json={"name": name}).json()["data"]


def _create_kp(client: TestClient, kb_id: int, title: str) -> dict:
    return client.post(f"/knowledge-bases/{kb_id}/knowledge-points", json={"title": title}).json()["data"]


def _write_answer(client: TestClient, kb_id: int, kp_id: int, content: str, effective_time: str, coord: dict | None = None) -> dict:
    return client.post(
        f"/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answers",
        json={"content": content, "effective_time": effective_time, "coord": coord or {}},
    ).json()["data"]


def _edit_answer(client: TestClient, kb_id: int, kp_id: int, answer_id: int, **kwargs) -> dict:
    return client.post(
        f"/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answers/{answer_id}/edit", json=kwargs
    ).json()["data"]


def _enable_dimension(db_engine: Engine, kb_id: int, key: str, label: str, field_type: str = "text") -> None:
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO dimension_definition (`key`, label, field_type) VALUES (:key, :label, :ft)"),
            {"key": key, "label": label, "ft": field_type},
        )
        conn.execute(
            text(
                "INSERT INTO knowledge_base_enabled_dimension (knowledge_base_id, dimension_key) "
                "VALUES (:kb, :key)"
            ),
            {"kb": kb_id, "key": key},
        )


def _groups_url(kb_id: int, kp_id: int) -> str:
    return f"/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answer-groups"


def test_answer_groups_for_live_unrevoked_chain(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-groups-live")
    kp = _create_kp(client, kb["id"], "kp-groups-live")
    _write_answer(client, kb["id"], kp["id"], "hello", "2026-08-01")

    resp = client.get(_groups_url(kb["id"], kp["id"]))
    assert resp.status_code == 200
    groups = resp.json()["data"]
    assert len(groups) == 1
    assert groups[0]["coord"] == {}
    assert groups[0]["revoked"] is False
    assert groups[0]["version_count"] == 1
    assert groups[0]["live_answer"]["content"] == "hello"
    assert groups[0]["latest_answer"]["content"] == "hello"


def test_answer_groups_shows_revoked_chain_that_compute_live_groups_would_hide(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    """The exact scenario the design doc §2 blocker is about: edit_answer's
    migration branch revokes the whole old chain when coord changes."""
    kb = _create_kb(client, "kb-groups-revoked")
    _enable_dimension(db_engine, kb["id"], "tenant", "租户")
    kp = _create_kp(client, kb["id"], "kp-groups-revoked")

    v1 = _write_answer(client, kb["id"], kp["id"], "v1", "2026-08-01", coord={"tenant": "acme"})
    _edit_answer(
        client,
        kb["id"],
        kp["id"],
        v1["id"],
        content="migrated",
        effective_time="2026-08-05",
        coord={"tenant": "other"},
        migration_reason="test migration",
    )

    resp = client.get(_groups_url(kb["id"], kp["id"]))
    groups = {frozenset(g["coord"].items()): g for g in resp.json()["data"]}
    assert len(groups) == 2

    old_group = groups[frozenset({"tenant": "acme"}.items())]
    assert old_group["revoked"] is True
    assert old_group["live_answer"] is None
    assert old_group["latest_answer"]["content"] == "v1"

    new_group = groups[frozenset({"tenant": "other"}.items())]
    assert new_group["revoked"] is False
    assert new_group["live_answer"]["content"] == "migrated"


def test_answer_groups_not_yet_effective_is_distinct_from_revoked(
    client: TestClient, migrated_schema
) -> None:
    """A chain with no revoked rows, but whose only version is later than
    `at`, must report revoked=False + live_answer=None — not be
    indistinguishable from an actually-revoked chain."""
    kb = _create_kb(client, "kb-groups-not-yet-effective")
    kp = _create_kp(client, kb["id"], "kp-groups-not-yet-effective")
    _write_answer(client, kb["id"], kp["id"], "future content", "2026-09-01")

    resp = client.get(_groups_url(kb["id"], kp["id"]), params={"at": "2026-08-01"})
    groups = resp.json()["data"]
    assert len(groups) == 1
    assert groups[0]["revoked"] is False
    assert groups[0]["live_answer"] is None
    assert groups[0]["latest_answer"]["content"] == "future content"


def test_answer_groups_deleted_knowledge_point_still_returns_its_history(client: TestClient, migrated_schema) -> None:
    """PRD §4.7: the detail page must keep showing a soft-deleted knowledge
    point's full historical answers ("以下仍可查看其全部历史答案") — unlike
    resolve_knowledge_point's "none" contract for third-party query
    consumers, this read-only view has no reason to hide them. Originally
    returned [] here (copied from the resolve endpoint's short-circuit
    without checking it applied) — issue #8's Codex outer-gate review caught
    that this silently emptied the detail page's answer tab for any deleted
    KP."""
    kb = _create_kb(client, "kb-groups-deleted-kp")
    kp = _create_kp(client, kb["id"], "kp-groups-deleted")
    _write_answer(client, kb["id"], kp["id"], "content", "2026-08-01")
    client.post(f"/knowledge-bases/{kb['id']}/knowledge-points/{kp['id']}/delete", json={"delete_reason": "x"})

    resp = client.get(_groups_url(kb["id"], kp["id"]))
    assert resp.status_code == 200
    groups = resp.json()["data"]
    assert len(groups) == 1
    assert groups[0]["latest_answer"]["content"] == "content"


def test_answer_groups_no_answers_returns_empty(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-groups-none")
    kp = _create_kp(client, kb["id"], "kp-groups-none")
    resp = client.get(_groups_url(kb["id"], kp["id"]))
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_answer_groups_nonexistent_kp_returns_404(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-groups-404")
    resp = client.get(_groups_url(kb["id"], 999999999))
    assert resp.status_code == 404


def test_answer_groups_nonexistent_kb_returns_404(client: TestClient, migrated_schema) -> None:
    resp = client.get(_groups_url(999999999, 1))
    assert resp.status_code == 404
