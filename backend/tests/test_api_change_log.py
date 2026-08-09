"""Integration tests for GET .../knowledge-points/{kp_id}/change-log and
GET /change-log (issue #12). See
docs/specs/2026-08-09-change-log-and-kb-stats-api-design.md.
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


def _kp_change_log_url(kb_id: int, kp_id: int) -> str:
    return f"/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/change-log"


def test_kp_change_log_write_then_edit_produces_two_rows(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-log-basic")
    kp = _create_kp(client, kb["id"], "kp-log-basic")
    a1 = _write_answer(client, kb["id"], kp["id"], "v1", "2026-08-01")
    _edit_answer(client, kb["id"], kp["id"], a1["id"], "v2", "2026-08-02")

    resp = client.get(_kp_change_log_url(kb["id"], kp["id"]))
    assert resp.status_code == 200
    rows = resp.json()["data"]
    assert len(rows) == 2

    newest, oldest = rows  # sorted descending by time
    assert oldest["action"] == "create"
    assert oldest["status"] == "superseded"
    assert oldest["before_content"] is None
    assert oldest["after_content"] == "v1"

    assert newest["action"] == "edit"
    assert newest["status"] == "live"
    assert newest["before_content"] == "v1"
    assert newest["after_content"] == "v2"
    assert newest["revocable"] is True


def test_kp_change_log_revoke_row_answer_id_can_be_used_to_actually_revoke(
    client: TestClient, migrated_schema
) -> None:
    kb = _create_kb(client, "kb-log-revoke-roundtrip")
    kp = _create_kp(client, kb["id"], "kp-log-revoke-roundtrip")
    answer = _write_answer(client, kb["id"], kp["id"], "content", "2026-08-01")

    rows = client.get(_kp_change_log_url(kb["id"], kp["id"])).json()["data"]
    assert len(rows) == 1
    assert rows[0]["revocable"] is True
    revocable_answer_id = rows[0]["answer_id"]
    assert revocable_answer_id == answer["id"]

    revoke_resp = client.post(
        f"{_answers_url(kb['id'], kp['id'])}/{revocable_answer_id}/revoke", json={"revoke_reason": "测试撤回"}
    )
    assert revoke_resp.status_code == 200

    rows_after = client.get(_kp_change_log_url(kb["id"], kp["id"])).json()["data"]
    assert len(rows_after) == 2
    revoke_row = next(r for r in rows_after if r["action"] == "revoke")
    assert revoke_row["revoke_reason"] == "测试撤回"
    assert revoke_row["answer_id"] == answer["id"]


def test_kp_change_log_whole_chain_revoke_keeps_non_last_versions_superseded(
    client: TestClient, migrated_schema
) -> None:
    kb = _create_kb(client, "kb-log-chain-revoke")
    kp = _create_kp(client, kb["id"], "kp-log-chain-revoke")
    a1 = _write_answer(client, kb["id"], kp["id"], "v1", "2026-08-01")
    a2 = _edit_answer(client, kb["id"], kp["id"], a1["id"], "v2", "2026-08-02")
    _revoke_answer(client, kb["id"], kp["id"], a2["id"], "整条链撤回")

    rows = client.get(_kp_change_log_url(kb["id"], kp["id"])).json()["data"]
    version_rows = sorted((r for r in rows if r["action"] in ("create", "edit")), key=lambda r: r["time"])
    assert [r["status"] for r in version_rows] == ["superseded", "revoked"]

    revoke_rows = [r for r in rows if r["action"] == "revoke"]
    assert len(revoke_rows) == 1
    assert revoke_rows[0]["revoke_reason"] == "整条链撤回"


def test_kp_change_log_for_deleted_knowledge_point_still_visible(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-log-deleted-kp")
    kp = _create_kp(client, kb["id"], "kp-log-deleted-kp")
    _write_answer(client, kb["id"], kp["id"], "content", "2026-08-01")
    client.post(f"/knowledge-bases/{kb['id']}/knowledge-points/{kp['id']}/delete", json={"delete_reason": "x"})

    resp = client.get(_kp_change_log_url(kb["id"], kp["id"]))
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1


def test_kp_change_log_nonexistent_kp_returns_404(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-log-404")
    resp = client.get(_kp_change_log_url(kb["id"], 999999))
    assert resp.status_code == 404


def test_kp_change_log_nonexistent_kb_returns_404(client: TestClient, migrated_schema) -> None:
    resp = client.get(_kp_change_log_url(999999, 1))
    assert resp.status_code == 404


def test_global_change_log_two_different_kbs_sharing_a_coord_do_not_get_spliced(
    client: TestClient, migrated_schema
) -> None:
    """Integration-level regression for F0: two knowledge points in two
    different knowledge bases, each only writing a default answer
    (coord={}, guaranteed identical coord_hash) — the global log must keep
    them as two separate chains with correctly attributed
    knowledge_base_name/knowledge_point_title, and neither's
    before_content must leak into the other's row."""
    kb_a = _create_kb(client, "kb-global-a")
    kb_b = _create_kb(client, "kb-global-b")
    kp_a = _create_kp(client, kb_a["id"], "kp-global-a")
    kp_b = _create_kp(client, kb_b["id"], "kp-global-b")
    _write_answer(client, kb_a["id"], kp_a["id"], "content-a", "2026-08-01")
    _write_answer(client, kb_b["id"], kp_b["id"], "content-b", "2026-08-02")

    rows = client.get("/change-log").json()["data"]
    row_a = next(r for r in rows if r["knowledge_point_id"] == kp_a["id"])
    row_b = next(r for r in rows if r["knowledge_point_id"] == kp_b["id"])

    assert row_a["action"] == "create"
    assert row_a["before_content"] is None
    assert row_a["after_content"] == "content-a"
    assert row_a["knowledge_base_id"] == kb_a["id"]
    assert row_a["knowledge_base_name"] == "kb-global-a"
    assert row_a["knowledge_point_title"] == "kp-global-a"

    assert row_b["action"] == "create"
    assert row_b["before_content"] is None
    assert row_b["after_content"] == "content-b"
    assert row_b["knowledge_base_id"] == kb_b["id"]
    assert row_b["knowledge_base_name"] == "kb-global-b"
    assert row_b["knowledge_point_title"] == "kp-global-b"


def test_global_change_log_includes_history_for_deleted_kp_and_deactivated_kb(
    client: TestClient, migrated_schema
) -> None:
    kb = _create_kb(client, "kb-global-deactivated")
    kp = _create_kp(client, kb["id"], "kp-global-deleted")
    _write_answer(client, kb["id"], kp["id"], "content", "2026-08-01")

    client.post(f"/knowledge-bases/{kb['id']}/knowledge-points/{kp['id']}/delete", json={"delete_reason": "x"})
    client.post(f"/knowledge-bases/{kb['id']}/deactivate")

    rows = client.get("/change-log").json()["data"]
    assert any(r["knowledge_point_id"] == kp["id"] for r in rows)
