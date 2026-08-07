from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _create(client: TestClient, name: str, description: str | None = None) -> dict:
    payload = {"name": name}
    if description is not None:
        payload["description"] = description
    resp = client.post("/knowledge-bases", json=payload)
    return resp


def test_create_knowledge_base_success(client: TestClient, migrated_schema) -> None:
    resp = _create(client, "kb-create-ok", "desc")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["msg"] == "操作成功"
    data = body["data"]
    assert data["name"] == "kb-create-ok"
    assert data["description"] == "desc"
    assert data["status"] == "active"
    assert data["active_knowledge_point_count"] == 0
    assert data["created_at"] is not None
    assert data["updated_at"] is not None
    assert data["id"] is not None


def test_create_knowledge_base_optional_description(client: TestClient, migrated_schema) -> None:
    resp = _create(client, "kb-create-no-desc")
    assert resp.status_code == 200
    assert resp.json()["data"]["description"] is None


def test_create_duplicate_name_against_active_kb_is_rejected(client: TestClient, migrated_schema) -> None:
    _create(client, "kb-dup-active")
    resp = _create(client, "kb-dup-active")
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 444
    assert "名称" in body["msg"]


def test_create_duplicate_name_against_deprecated_kb_is_rejected(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    created = _create(client, "kb-dup-deprecated").json()["data"]
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE knowledge_base SET status = 'deprecated' WHERE id = :kb"), {"kb": created["id"]}
        )
    resp = _create(client, "kb-dup-deprecated")
    assert resp.status_code == 400
    assert resp.json()["code"] == 444


def test_create_blank_name_is_rejected_with_422(client: TestClient, migrated_schema) -> None:
    resp = _create(client, "   ")
    assert resp.status_code == 422
    assert resp.json()["code"] == 444


def test_list_returns_both_active_and_deprecated_with_status_field(
    client: TestClient, migrated_schema
) -> None:
    kb1 = _create(client, "kb-list-active").json()["data"]
    kb2 = _create(client, "kb-list-deprecated").json()["data"]
    client.post(f"/knowledge-bases/{kb2['id']}/deactivate")

    resp = client.get("/knowledge-bases")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    by_id = {row["id"]: row for row in body["data"]}
    assert by_id[kb1["id"]]["status"] == "active"
    assert by_id[kb2["id"]]["status"] == "deprecated"


def test_list_filters_by_status_query_param(client: TestClient, migrated_schema) -> None:
    kb1 = _create(client, "kb-filter-active").json()["data"]
    kb2 = _create(client, "kb-filter-deprecated").json()["data"]
    client.post(f"/knowledge-bases/{kb2['id']}/deactivate")

    active_only = client.get("/knowledge-bases", params={"status": "active"}).json()["data"]
    active_ids = {row["id"] for row in active_only}
    assert kb1["id"] in active_ids
    assert kb2["id"] not in active_ids

    deprecated_only = client.get("/knowledge-bases", params={"status": "deprecated"}).json()["data"]
    deprecated_ids = {row["id"] for row in deprecated_only}
    assert kb2["id"] in deprecated_ids
    assert kb1["id"] not in deprecated_ids


def test_list_active_knowledge_point_count_excludes_deleted_points(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create(client, "kb-with-points").json()["data"]
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO knowledge_point (knowledge_base_id, title, status) "
                "VALUES (:kb, 'kp-active', 'active')"
            ),
            {"kb": kb["id"]},
        )
        conn.execute(
            text(
                "INSERT INTO knowledge_point (knowledge_base_id, title, status) "
                "VALUES (:kb, 'kp-deleted', 'deleted')"
            ),
            {"kb": kb["id"]},
        )

    resp = client.get("/knowledge-bases")
    row = next(r for r in resp.json()["data"] if r["id"] == kb["id"])
    assert row["active_knowledge_point_count"] == 1


def test_update_name_and_description_success(client: TestClient, migrated_schema) -> None:
    kb = _create(client, "kb-update-me", "old desc").json()["data"]
    resp = client.patch(f"/knowledge-bases/{kb['id']}", json={"name": "kb-updated", "description": "new desc"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "kb-updated"
    assert data["description"] == "new desc"


def test_update_description_only_does_not_false_positive_self_duplicate(
    client: TestClient, migrated_schema
) -> None:
    kb = _create(client, "kb-self-rename").json()["data"]
    resp = client.patch(f"/knowledge-bases/{kb['id']}", json={"description": "only desc changed"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "kb-self-rename"


def test_update_name_to_existing_other_kb_name_is_rejected(client: TestClient, migrated_schema) -> None:
    _create(client, "kb-taken-name")
    kb2 = _create(client, "kb-wants-rename").json()["data"]
    resp = client.patch(f"/knowledge-bases/{kb2['id']}", json={"name": "kb-taken-name"})
    assert resp.status_code == 400
    assert resp.json()["code"] == 444


def test_update_nonexistent_id_returns_404(client: TestClient, migrated_schema) -> None:
    resp = client.patch("/knowledge-bases/999999999", json={"name": "does-not-matter"})
    assert resp.status_code == 404
    assert resp.json()["code"] == 444


def test_deactivate_then_activate_round_trip(client: TestClient, migrated_schema) -> None:
    kb = _create(client, "kb-toggle").json()["data"]

    deactivated = client.post(f"/knowledge-bases/{kb['id']}/deactivate")
    assert deactivated.status_code == 200
    assert deactivated.json()["data"]["status"] == "deprecated"

    activated = client.post(f"/knowledge-bases/{kb['id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["data"]["status"] == "active"


def test_deactivate_is_idempotent_and_does_not_bump_updated_at(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create(client, "kb-idempotent-deactivate").json()["data"]
    first = client.post(f"/knowledge-bases/{kb['id']}/deactivate").json()["data"]

    with db_engine.begin() as conn:
        conn.execute(text("SELECT SLEEP(0.05)"))

    second = client.post(f"/knowledge-bases/{kb['id']}/deactivate")
    assert second.status_code == 200
    assert second.json()["data"]["status"] == "deprecated"
    assert second.json()["data"]["updated_at"] == first["updated_at"]


def test_activate_nonexistent_id_returns_404(client: TestClient, migrated_schema) -> None:
    resp = client.post("/knowledge-bases/999999999/activate")
    assert resp.status_code == 404
    assert resp.json()["code"] == 444


def test_deactivate_nonexistent_id_returns_404(client: TestClient, migrated_schema) -> None:
    resp = client.post("/knowledge-bases/999999999/deactivate")
    assert resp.status_code == 404
    assert resp.json()["code"] == 444
