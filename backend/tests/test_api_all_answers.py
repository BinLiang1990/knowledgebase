"""Tests for GET .../knowledge-points/{kp_id}/answers (issue #14). See
docs/specs/2026-08-09-timeline-changelog-and-global-log-frontend-design.md §1.
"""
from fastapi.testclient import TestClient


def _create_kb(client: TestClient, name: str) -> dict:
    return client.post("/knowledge-bases", json={"name": name}).json()["data"]


def _create_kp(client: TestClient, kb_id: int, title: str) -> dict:
    return client.post(f"/knowledge-bases/{kb_id}/knowledge-points", json={"title": title}).json()["data"]


def _answers_url(kb_id: int, kp_id: int) -> str:
    return f"/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answers"


def _write_answer(client: TestClient, kb_id: int, kp_id: int, content: str, effective_time: str) -> dict:
    return client.post(
        _answers_url(kb_id, kp_id), json={"content": content, "effective_time": effective_time}
    ).json()["data"]


def _edit_answer(client: TestClient, kb_id: int, kp_id: int, answer_id: int, content: str, effective_time: str) -> dict:
    return client.post(
        f"{_answers_url(kb_id, kp_id)}/{answer_id}/edit",
        json={"content": content, "effective_time": effective_time},
    ).json()["data"]


def _revoke_answer(client: TestClient, kb_id: int, kp_id: int, answer_id: int, reason: str) -> dict:
    return client.post(
        f"{_answers_url(kb_id, kp_id)}/{answer_id}/revoke", json={"revoke_reason": reason}
    ).json()["data"]


def test_returns_every_version_unfiltered(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-all-answers")
    kp = _create_kp(client, kb["id"], "kp-all-answers")
    a1 = _write_answer(client, kb["id"], kp["id"], "v1", "2026-08-01")
    _edit_answer(client, kb["id"], kp["id"], a1["id"], "v2", "2026-08-02")
    _revoke_answer(client, kb["id"], kp["id"], a1["id"], "test revoke")

    resp = client.get(_answers_url(kb["id"], kp["id"]))
    assert resp.status_code == 200
    rows = resp.json()["data"]
    assert len(rows) == 2
    assert {r["content"] for r in rows} == {"v1", "v2"}
    assert all(r["revoked"] for r in rows)


def test_returns_answers_across_multiple_coord_groups(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-all-answers-groups")
    kp = _create_kp(client, kb["id"], "kp-all-answers-groups")
    _write_answer(client, kb["id"], kp["id"], "default content", "2026-08-01")

    resp = client.get(_answers_url(kb["id"], kp["id"]))
    rows = resp.json()["data"]
    assert len(rows) == 1
    assert rows[0]["coord"] == {}


def test_visible_for_a_soft_deleted_knowledge_point(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-all-answers-deleted")
    kp = _create_kp(client, kb["id"], "kp-all-answers-deleted")
    _write_answer(client, kb["id"], kp["id"], "content", "2026-08-01")
    client.post(f"/knowledge-bases/{kb['id']}/knowledge-points/{kp['id']}/delete", json={"delete_reason": "x"})

    resp = client.get(_answers_url(kb["id"], kp["id"]))
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1


def test_nonexistent_kp_returns_404(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-all-answers-404")
    resp = client.get(_answers_url(kb["id"], 999999))
    assert resp.status_code == 404


def test_nonexistent_kb_returns_404(client: TestClient, migrated_schema) -> None:
    resp = client.get(_answers_url(999999, 1))
    assert resp.status_code == 404


def test_does_not_leak_answers_from_a_different_knowledge_point(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-all-answers-isolation")
    kp_a = _create_kp(client, kb["id"], "kp-a")
    kp_b = _create_kp(client, kb["id"], "kp-b")
    _write_answer(client, kb["id"], kp_a["id"], "content-a", "2026-08-01")
    _write_answer(client, kb["id"], kp_b["id"], "content-b", "2026-08-01")

    rows_a = client.get(_answers_url(kb["id"], kp_a["id"])).json()["data"]
    assert len(rows_a) == 1
    assert rows_a[0]["content"] == "content-a"
