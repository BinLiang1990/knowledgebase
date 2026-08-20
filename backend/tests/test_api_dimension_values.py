"""GET /knowledge-bases/{id}/dimension-values —— 条件筛选下拉的候选取值。

口径：未撤回 + 知识点未删（与 resolve 可命中范围一致），跨知识库隔离，
去重按字面排序。
"""
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


def _create_kp(client: TestClient, kb_id: int, title: str) -> dict:
    return client.post(
        f"/knowledge-bases/{kb_id}/knowledge-points", json={"title": title}
    ).json()["data"]


def _write_answer(client: TestClient, kb_id: int, kp_id: int, coord: dict, content: str = "内容") -> dict:
    resp = client.post(
        f"/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answers",
        json={"coord": coord, "content": content, "effective_time": "2026-01-01"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _get_values(client: TestClient, kb_id: int, key: str):
    return client.get(
        f"/knowledge-bases/{kb_id}/dimension-values", params={"dimension_key": key}
    )


def test_values_deduped_and_sorted_across_kps_and_versions(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    _insert_dimension(db_engine, "tenant", "租户")
    kb = _create_kb(client, "kb-dim-values")
    _enable_dimension(db_engine, kb["id"], "tenant")

    kp1 = _create_kp(client, kb["id"], "kp-1")
    kp2 = _create_kp(client, kb["id"], "kp-2")
    _write_answer(client, kb["id"], kp1["id"], {"tenant": "beta"})
    # 同一条件链的第二个版本：不产生重复候选
    _write_answer(client, kb["id"], kp1["id"], {"tenant": "beta"}, content="v2")
    _write_answer(client, kb["id"], kp2["id"], {"tenant": "Acme"})
    # 默认答案（coord={}）不含该维度：不产生候选
    _write_answer(client, kb["id"], kp2["id"], {})

    resp = _get_values(client, kb["id"], "tenant")
    assert resp.status_code == 200
    assert resp.json()["data"] == ["Acme", "beta"]


def test_values_scoped_to_requested_kb(client: TestClient, migrated_schema, db_engine: Engine) -> None:
    _insert_dimension(db_engine, "tenant", "租户")
    kb_a = _create_kb(client, "kb-values-a")
    kb_b = _create_kb(client, "kb-values-b")
    _enable_dimension(db_engine, kb_a["id"], "tenant")
    _enable_dimension(db_engine, kb_b["id"], "tenant")

    kp_a = _create_kp(client, kb_a["id"], "kp-a")
    kp_b = _create_kp(client, kb_b["id"], "kp-b")
    _write_answer(client, kb_a["id"], kp_a["id"], {"tenant": "only-in-a"})
    _write_answer(client, kb_b["id"], kp_b["id"], {"tenant": "only-in-b"})

    assert _get_values(client, kb_a["id"], "tenant").json()["data"] == ["only-in-a"]
    assert _get_values(client, kb_b["id"], "tenant").json()["data"] == ["only-in-b"]


def test_values_exclude_revoked_chain(client: TestClient, migrated_schema, db_engine: Engine) -> None:
    _insert_dimension(db_engine, "tenant", "租户")
    kb = _create_kb(client, "kb-values-revoked")
    _enable_dimension(db_engine, kb["id"], "tenant")

    kp = _create_kp(client, kb["id"], "kp")
    _write_answer(client, kb["id"], kp["id"], {"tenant": "kept"})
    gone = _write_answer(client, kb["id"], kp["id"], {"tenant": "gone"})
    resp = client.post(
        f"/knowledge-bases/{kb['id']}/knowledge-points/{kp['id']}/answers/{gone['id']}/revoke",
        json={"revoke_reason": "测试撤回"},
    )
    assert resp.status_code == 200

    assert _get_values(client, kb["id"], "tenant").json()["data"] == ["kept"]


def test_values_exclude_deleted_knowledge_point(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    _insert_dimension(db_engine, "tenant", "租户")
    kb = _create_kb(client, "kb-values-deleted-kp")
    _enable_dimension(db_engine, kb["id"], "tenant")

    kp_live = _create_kp(client, kb["id"], "kp-live")
    kp_dead = _create_kp(client, kb["id"], "kp-dead")
    _write_answer(client, kb["id"], kp_live["id"], {"tenant": "live"})
    _write_answer(client, kb["id"], kp_dead["id"], {"tenant": "dead"})
    resp = client.post(
        f"/knowledge-bases/{kb['id']}/knowledge-points/{kp_dead['id']}/delete",
        json={"delete_reason": "测试删除"},
    )
    assert resp.status_code == 200

    assert _get_values(client, kb["id"], "tenant").json()["data"] == ["live"]


def test_values_resolve_collation_equivalent_key_spelling(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    """key 列是 utf8mb4_0900_ai_ci：请求拼写 "Tenant" 应命中规范 key
    "tenant"（镜像 dimension.py _set_status 的 canonical-key 处理）。"""
    _insert_dimension(db_engine, "tenant", "租户")
    kb = _create_kb(client, "kb-values-collation")
    _enable_dimension(db_engine, kb["id"], "tenant")
    kp = _create_kp(client, kb["id"], "kp")
    _write_answer(client, kb["id"], kp["id"], {"tenant": "acme"})

    assert _get_values(client, kb["id"], "Tenant").json()["data"] == ["acme"]


def test_values_empty_when_no_answers(client: TestClient, migrated_schema, db_engine: Engine) -> None:
    _insert_dimension(db_engine, "tenant", "租户")
    kb = _create_kb(client, "kb-values-empty")
    _enable_dimension(db_engine, kb["id"], "tenant")

    resp = _get_values(client, kb["id"], "tenant")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_values_400_for_dimension_not_enabled_here(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    # 全局存在但本库未启用，与全局不存在同一个口径：都报「未在本知识库启用」
    _insert_dimension(db_engine, "tenant", "租户")
    kb = _create_kb(client, "kb-values-not-enabled")

    resp = _get_values(client, kb["id"], "tenant")
    assert resp.status_code == 400
    assert "未在本知识库启用" in resp.json()["msg"]

    resp = _get_values(client, kb["id"], "no-such-dim")
    assert resp.status_code == 400


def test_values_404_for_unknown_kb(client: TestClient, migrated_schema) -> None:
    resp = _get_values(client, 999999, "tenant")
    assert resp.status_code == 404
