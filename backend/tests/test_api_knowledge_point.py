from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _create_kb(client: TestClient, name: str) -> dict:
    return client.post("/knowledge-bases", json={"name": name}).json()["data"]


def _kp_base(kb_id: int) -> str:
    return f"/knowledge-bases/{kb_id}/knowledge-points"


def _create_kp(client: TestClient, kb_id: int, title: str, default_answer: dict | None = None) -> dict:
    payload = {"title": title}
    if default_answer is not None:
        payload["default_answer"] = default_answer
    return client.post(_kp_base(kb_id), json=payload).json()["data"]


def test_create_knowledge_point_without_default_answer(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-kp-basic")
    resp = client.post(_kp_base(kb["id"]), json={"title": "kp-1"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["title"] == "kp-1"
    assert data["status"] == "active"
    assert data["knowledge_base_id"] == kb["id"]
    assert data["active_answer_count"] == 0
    assert data["operator"] == "admin"


def test_create_knowledge_point_with_default_answer_creates_both_atomically(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create_kb(client, "kb-kp-with-default")
    resp = client.post(
        _kp_base(kb["id"]),
        json={
            "title": "kp-with-default",
            "default_answer": {"content": "default content", "effective_time": "2026-08-08"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["active_answer_count"] == 1

    with db_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT coord, coord_hash, content, source FROM answer WHERE knowledge_point_id = :kp"),
            {"kp": data["id"]},
        ).all()
    assert len(rows) == 1
    assert rows[0][0] == "{}"
    assert rows[0][2] == "default content"
    assert rows[0][3] == "人工填报"


def test_create_knowledge_point_duplicate_title_in_same_kb_is_rejected(
    client: TestClient, migrated_schema
) -> None:
    kb = _create_kb(client, "kb-kp-dup")
    _create_kp(client, kb["id"], "dup-title")
    resp = client.post(_kp_base(kb["id"]), json={"title": "dup-title"})
    assert resp.status_code == 400
    assert resp.json()["code"] == 444


def test_create_knowledge_point_duplicate_title_against_deleted_kp_is_rejected(
    client: TestClient, migrated_schema
) -> None:
    kb = _create_kb(client, "kb-kp-dup-deleted")
    kp = _create_kp(client, kb["id"], "will-be-deleted")
    client.post(f"{_kp_base(kb['id'])}/{kp['id']}/delete", json={"delete_reason": "test"})
    resp = client.post(_kp_base(kb["id"]), json={"title": "will-be-deleted"})
    assert resp.status_code == 400


def test_create_knowledge_point_same_title_different_kb_is_allowed(
    client: TestClient, migrated_schema
) -> None:
    kb1 = _create_kb(client, "kb-kp-cross-1")
    kb2 = _create_kb(client, "kb-kp-cross-2")
    _create_kp(client, kb1["id"], "shared-title")
    resp = client.post(_kp_base(kb2["id"]), json={"title": "shared-title"})
    assert resp.status_code == 200


def test_list_knowledge_points_defaults_to_active_only(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-kp-list-default")
    kp1 = _create_kp(client, kb["id"], "kp-active")
    kp2 = _create_kp(client, kb["id"], "kp-deleted")
    client.post(f"{_kp_base(kb['id'])}/{kp2['id']}/delete", json={"delete_reason": "x"})

    resp = client.get(_kp_base(kb["id"]))
    ids = {row["id"] for row in resp.json()["data"]}
    assert kp1["id"] in ids
    assert kp2["id"] not in ids


def test_list_knowledge_points_status_deleted_filter_shows_recycle_bin(
    client: TestClient, migrated_schema
) -> None:
    kb = _create_kb(client, "kb-kp-list-deleted")
    kp = _create_kp(client, kb["id"], "kp-to-recycle")
    client.post(f"{_kp_base(kb['id'])}/{kp['id']}/delete", json={"delete_reason": "x"})

    resp = client.get(_kp_base(kb["id"]), params={"status": "deleted"})
    ids = {row["id"] for row in resp.json()["data"]}
    assert kp["id"] in ids


def test_get_knowledge_point_detail(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-kp-detail")
    kp = _create_kp(client, kb["id"], "kp-detail")
    resp = client.get(f"{_kp_base(kb['id'])}/{kp['id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "kp-detail"


def test_get_knowledge_point_nonexistent_returns_404(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-kp-404")
    resp = client.get(f"{_kp_base(kb['id'])}/999999999")
    assert resp.status_code == 404
    assert resp.json()["code"] == 444


def test_get_knowledge_point_nonexistent_kb_returns_404(client: TestClient, migrated_schema) -> None:
    resp = client.get("/knowledge-bases/999999999/knowledge-points/1")
    assert resp.status_code == 404


def test_rename_knowledge_point_success(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-kp-rename")
    kp = _create_kp(client, kb["id"], "old-title")
    resp = client.patch(f"{_kp_base(kb['id'])}/{kp['id']}", json={"title": "new-title"})
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "new-title"


def test_rename_to_existing_title_is_rejected(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-kp-rename-dup")
    _create_kp(client, kb["id"], "taken-title")
    kp2 = _create_kp(client, kb["id"], "wants-rename")
    resp = client.patch(f"{_kp_base(kb['id'])}/{kp2['id']}", json={"title": "taken-title"})
    assert resp.status_code == 400


def test_rename_to_same_title_is_not_a_false_positive_duplicate(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-kp-rename-self")
    kp = _create_kp(client, kb["id"], "same-title")
    resp = client.patch(f"{_kp_base(kb['id'])}/{kp['id']}", json={"title": "same-title"})
    assert resp.status_code == 200


def test_rename_deleted_knowledge_point_is_rejected(client: TestClient, migrated_schema) -> None:
    """Consistent with create_answer/edit_answer's own "已删除，无法..." guard
    (Kimi 终审 finding on PR #24) — a soft-deleted knowledge point is
    read-only everywhere except delete/restore. Previously a direct PATCH
    could rename a deleted KP even though the detail page's UI hides the
    "编辑标题" button for exactly this state."""
    kb = _create_kb(client, "kb-kp-rename-deleted")
    kp = _create_kp(client, kb["id"], "old-title")
    client.post(f"{_kp_base(kb['id'])}/{kp['id']}/delete", json={"delete_reason": "x"})

    resp = client.patch(f"{_kp_base(kb['id'])}/{kp['id']}", json={"title": "new-title"})
    assert resp.status_code == 400
    assert resp.json()["code"] == 444


def test_delete_requires_reason(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-kp-delete-noreason")
    kp = _create_kp(client, kb["id"], "kp-no-reason")
    resp = client.post(f"{_kp_base(kb['id'])}/{kp['id']}/delete", json={"delete_reason": ""})
    assert resp.status_code == 422


def test_delete_then_restore_round_trip(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-kp-delete-restore")
    kp = _create_kp(client, kb["id"], "kp-round-trip")

    deleted = client.post(f"{_kp_base(kb['id'])}/{kp['id']}/delete", json={"delete_reason": "test reason"})
    assert deleted.status_code == 200
    assert deleted.json()["data"]["status"] == "deleted"
    assert deleted.json()["data"]["delete_reason"] == "test reason"

    restored = client.post(f"{_kp_base(kb['id'])}/{kp['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["data"]["status"] == "active"


def test_delete_is_idempotent_and_keeps_original_reason(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-kp-delete-idempotent")
    kp = _create_kp(client, kb["id"], "kp-idempotent-delete")

    first = client.post(f"{_kp_base(kb['id'])}/{kp['id']}/delete", json={"delete_reason": "first reason"})
    assert first.json()["data"]["delete_reason"] == "first reason"

    second = client.post(f"{_kp_base(kb['id'])}/{kp['id']}/delete", json={"delete_reason": "retry reason"})
    assert second.status_code == 200
    assert second.json()["data"]["delete_reason"] == "first reason"


def test_restore_is_idempotent(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-kp-restore-idempotent")
    kp = _create_kp(client, kb["id"], "kp-idempotent-restore")
    resp = client.post(f"{_kp_base(kb['id'])}/{kp['id']}/restore")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "active"


def test_deleted_knowledge_point_still_readable(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-kp-deleted-readable")
    kp = _create_kp(client, kb["id"], "kp-still-readable")
    client.post(f"{_kp_base(kb['id'])}/{kp['id']}/delete", json={"delete_reason": "x"})

    resp = client.get(f"{_kp_base(kb['id'])}/{kp['id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "deleted"


def test_active_answer_count_excludes_revoked_answers(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create_kb(client, "kb-kp-answer-count")
    kp = _create_kp(client, kb["id"], "kp-answer-count")
    client.post(f"{_kp_base(kb['id'])}/{kp['id']}/answers", json={"content": "c1", "effective_time": "2026-08-08"})
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO answer (knowledge_base_id, knowledge_point_id, coord, coord_hash, "
                "content, effective_time, revoked) VALUES (:kb, :kp, '{}', :hash, 'revoked-one', "
                "'2026-08-08', 1)"
            ),
            {"kb": kb["id"], "kp": kp["id"], "hash": "1" * 64},
        )

    resp = client.get(f"{_kp_base(kb['id'])}/{kp['id']}")
    assert resp.json()["data"]["active_answer_count"] == 1
