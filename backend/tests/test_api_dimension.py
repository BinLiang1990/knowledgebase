from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _insert_dimension(
    db_engine: Engine, key: str, label: str, field_type: str = "text", status: str = "active"
) -> None:
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO dimension_definition (`key`, label, field_type, status) "
                "VALUES (:key, :label, :field_type, :status)"
            ),
            {"key": key, "label": label, "field_type": field_type, "status": status},
        )


def _create_kb(client: TestClient, name: str) -> dict:
    return client.post("/knowledge-bases", json={"name": name}).json()["data"]


def _enable_dimension(db_engine: Engine, kb_id: int, dimension_key: str) -> None:
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO knowledge_base_enabled_dimension (knowledge_base_id, dimension_key) "
                "VALUES (:kb, :key)"
            ),
            {"kb": kb_id, "key": dimension_key},
        )


def test_list_dimensions_excludes_deprecated(client: TestClient, migrated_schema, db_engine: Engine) -> None:
    _insert_dimension(db_engine, "tenant", "租户", status="active")
    _insert_dimension(db_engine, "old_dim", "旧维度", status="deprecated")

    resp = client.get("/dimensions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    keys = {row["key"] for row in body["data"]}
    assert "tenant" in keys
    assert "old_dim" not in keys


def test_list_dimensions_returns_exact_field_shape(client: TestClient, migrated_schema, db_engine: Engine) -> None:
    _insert_dimension(db_engine, "region", "地区", field_type="text")
    resp = client.get("/dimensions")
    row = next(r for r in resp.json()["data"] if r["key"] == "region")
    assert set(row.keys()) == {"key", "label", "field_type", "weight"}
    assert row["label"] == "地区"
    assert row["field_type"] == "text"
    assert isinstance(row["weight"], int)


def test_enabled_dimensions_returns_full_definitions(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    _insert_dimension(db_engine, "tenant", "租户")
    kb = _create_kb(client, "kb-enabled-dims")
    _enable_dimension(db_engine, kb["id"], "tenant")

    resp = client.get(f"/knowledge-bases/{kb['id']}/enabled-dimensions")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0] == {"key": "tenant", "label": "租户", "field_type": "text", "weight": 50}


def test_enabled_dimensions_excludes_globally_deprecated_dimension(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    """Core rule from PRD §4.3: globally deactivating a dimension removes it
    from every knowledge base's enabled list, even though the join-table row
    (knowledge_base_enabled_dimension) is untouched."""
    _insert_dimension(db_engine, "region", "地区", status="active")
    kb = _create_kb(client, "kb-dim-gets-deprecated")
    _enable_dimension(db_engine, kb["id"], "region")

    still_there = client.get(f"/knowledge-bases/{kb['id']}/enabled-dimensions").json()["data"]
    assert len(still_there) == 1

    with db_engine.begin() as conn:
        conn.execute(text("UPDATE dimension_definition SET status = 'deprecated' WHERE `key` = 'region'"))

    resp = client.get(f"/knowledge-bases/{kb['id']}/enabled-dimensions")
    assert resp.json()["data"] == []


def test_enabled_dimensions_empty_when_none_enabled(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-no-dims")
    resp = client.get(f"/knowledge-bases/{kb['id']}/enabled-dimensions")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_enabled_dimensions_for_deprecated_kb_still_returns_list(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    """Judgment call documented in design doc §3.3: a deactivated knowledge
    base's enabled-dimensions are still queryable (read-only, no PRD text
    blocks it). Locked in here so a future clarification shows up as a
    deliberate test change, not a silent regression."""
    _insert_dimension(db_engine, "tenant", "租户")
    kb = _create_kb(client, "kb-deprecated-dims")
    _enable_dimension(db_engine, kb["id"], "tenant")
    client.post(f"/knowledge-bases/{kb['id']}/deactivate")

    resp = client.get(f"/knowledge-bases/{kb['id']}/enabled-dimensions")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1


def test_enabled_dimensions_nonexistent_kb_returns_404(client: TestClient, migrated_schema) -> None:
    resp = client.get("/knowledge-bases/999999999/enabled-dimensions")
    assert resp.status_code == 404
    assert resp.json()["code"] == 444
