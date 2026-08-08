"""API tests for issue #5's resolve endpoints, including a regression suite
rebuilt from frontend-mock/assets/app.js's seed data — see
docs/specs/2026-08-08-resolve-engine-design.md §5.2."""
import json

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy import text


def _create_kb(client: TestClient, name: str) -> dict:
    return client.post("/knowledge-bases", json={"name": name}).json()["data"]


def _create_kp(client: TestClient, kb_id: int, title: str) -> dict:
    return client.post(f"/knowledge-bases/{kb_id}/knowledge-points", json={"title": title}).json()["data"]


def _write_answer(client: TestClient, kb_id: int, kp_id: int, content: str, effective_time: str, coord: dict | None = None, note: str | None = None) -> dict:
    payload = {"content": content, "effective_time": effective_time, "coord": coord or {}}
    if note is not None:
        payload["note"] = note
    return client.post(
        f"/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answers", json=payload
    ).json()["data"]


def _enable_dimension(db_engine: Engine, kb_id: int, key: str, label: str, field_type: str = "text", weight: int | None = None) -> None:
    with db_engine.begin() as conn:
        if weight is None:
            conn.execute(
                text("INSERT INTO dimension_definition (`key`, label, field_type) VALUES (:key, :label, :ft)"),
                {"key": key, "label": label, "ft": field_type},
            )
        else:
            conn.execute(
                text(
                    "INSERT INTO dimension_definition (`key`, label, field_type, weight) "
                    "VALUES (:key, :label, :ft, :weight)"
                ),
                {"key": key, "label": label, "ft": field_type, "weight": weight},
            )
        conn.execute(
            text(
                "INSERT INTO knowledge_base_enabled_dimension (knowledge_base_id, dimension_key) "
                "VALUES (:kb, :key)"
            ),
            {"kb": kb_id, "key": key},
        )


def _resolve_url(kb_id: int, kp_id: int) -> str:
    return f"/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/resolve"


def _resolve(client: TestClient, kb_id: int, kp_id: int, at: str | None = None, coord: dict | None = None):
    params = {}
    if at is not None:
        params["at"] = at
    if coord is not None:
        params["coord"] = json.dumps(coord)
    return client.get(_resolve_url(kb_id, kp_id), params=params)


# ---------------------------------------------------------------------------
# Regression suite rebuilt from frontend-mock's seed data (退款政策 / KP #1
# under 产品知识库), verified by hand against resolveAnswer/liveGroups in
# frontend-mock/assets/app.js — see design doc §5.2.
# ---------------------------------------------------------------------------


def _seed_refund_policy_kp(client: TestClient, db_engine: Engine) -> tuple[dict, dict]:
    kb = _create_kb(client, "产品知识库-regression")
    _enable_dimension(db_engine, kb["id"], "tenant", "租户", weight=90)
    kp = _create_kp(client, kb["id"], "退款政策")
    _write_answer(client, kb["id"], kp["id"], "订单支付完成后 7 天内，未使用/未核销的订单支持无理由退款。", "2026-08-01")
    _write_answer(client, kb["id"], kp["id"], "退款政策已更新：无理由退款期限从 7 天延长至 15 天，超期需人工审核。", "2026-08-06")
    _write_answer(
        client, kb["id"], kp["id"], "「示例租户B」按合同约定执行 30 天无理由退款，与默认政策不同。",
        "2026-08-05", coord={"tenant": "示例租户B"},
    )
    return kb, kp


def test_regression_default_answer_fallback_at_mock_now(client: TestClient, migrated_schema, db_engine: Engine) -> None:
    kb, kp = _seed_refund_policy_kp(client, db_engine)
    resp = _resolve(client, kb["id"], kp["id"], at="2026-08-06")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "default"
    assert "15 天" in data["answer"]["content"]


def test_regression_exact_match_on_tenant(client: TestClient, migrated_schema, db_engine: Engine) -> None:
    kb, kp = _seed_refund_policy_kp(client, db_engine)
    resp = _resolve(client, kb["id"], kp["id"], at="2026-08-06", coord={"tenant": "示例租户B"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "exact"
    assert "30 天" in data["answer"]["content"]


def test_regression_weighted_fallback_for_unmatched_tenant(client: TestClient, migrated_schema, db_engine: Engine) -> None:
    kb, kp = _seed_refund_policy_kp(client, db_engine)
    resp = _resolve(client, kb["id"], kp["id"], at="2026-08-06", coord={"tenant": "从未出现过的租户"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "weighted"
    assert "15 天" in data["answer"]["content"]


def test_regression_none_before_any_answer_existed(client: TestClient, migrated_schema, db_engine: Engine) -> None:
    kb, kp = _seed_refund_policy_kp(client, db_engine)
    resp = _resolve(client, kb["id"], kp["id"], at="2026-07-25")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "none"
    assert data["answer"] is None


# ---------------------------------------------------------------------------
# Single-resolve endpoint: error paths
# ---------------------------------------------------------------------------


def test_resolve_nonexistent_kp_returns_404(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-resolve-404")
    resp = _resolve(client, kb["id"], 999999999)
    assert resp.status_code == 404


def test_resolve_coord_with_dimension_not_enabled_is_rejected(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-resolve-dim-not-enabled")
    kp = _create_kp(client, kb["id"], "kp-resolve-dim-not-enabled")
    resp = _resolve(client, kb["id"], kp["id"], coord={"tenant": "acme"})
    assert resp.status_code == 400


def test_resolve_malformed_coord_json_returns_422(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-resolve-bad-json")
    kp = _create_kp(client, kb["id"], "kp-resolve-bad-json")
    resp = client.get(_resolve_url(kb["id"], kp["id"]), params={"coord": "{not valid json"})
    assert resp.status_code == 422


def test_resolve_coord_not_a_json_object_returns_422(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-resolve-non-object")
    kp = _create_kp(client, kb["id"], "kp-resolve-non-object")
    resp = client.get(_resolve_url(kb["id"], kp["id"]), params={"coord": "[1,2,3]"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# List + filter endpoint
# ---------------------------------------------------------------------------


def _list_url(kb_id: int) -> str:
    return f"/knowledge-bases/{kb_id}/knowledge-points"


def test_list_includes_resolved_field_with_no_filters(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-list-resolved-default")
    kp = _create_kp(client, kb["id"], "kp-list-resolved-default")
    _write_answer(client, kb["id"], kp["id"], "default content", "2026-08-08")

    resp = client.get(_list_url(kb["id"]))
    assert resp.status_code == 200
    row = next(r for r in resp.json()["data"] if r["id"] == kp["id"])
    assert row["resolved"]["status"] == "default"
    assert row["resolved"]["answer"]["content"] == "default content"


def test_list_keyword_filter_is_case_insensitive_substring(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-list-keyword")
    _create_kp(client, kb["id"], "Refund Policy")
    _create_kp(client, kb["id"], "Invoice Process")

    resp = client.get(_list_url(kb["id"]), params={"keyword": "refund"})
    titles = [r["title"] for r in resp.json()["data"]]
    assert titles == ["Refund Policy"]


def test_list_with_coord_excludes_none_matches(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create_kb(client, "kb-list-coord-exclude")
    _enable_dimension(db_engine, kb["id"], "tenant", "租户")
    matching = _create_kp(client, kb["id"], "kp-matching")
    _write_answer(client, kb["id"], matching["id"], "acme content", "2026-08-08", coord={"tenant": "acme"})
    no_match = _create_kp(client, kb["id"], "kp-no-match")
    _write_answer(client, kb["id"], no_match["id"], "other content", "2026-08-08", coord={"tenant": "other"})

    resp = client.get(_list_url(kb["id"]), params={"coord": json.dumps({"tenant": "acme"})})
    ids = {r["id"] for r in resp.json()["data"]}
    assert matching["id"] in ids
    assert no_match["id"] not in ids


def test_list_without_coord_shows_knowledge_point_with_no_answers(client: TestClient, migrated_schema) -> None:
    """Without a coord filter, even a KP with zero answers (resolved
    status="none") still appears — only a non-empty coord filter excludes
    non-matching KPs (design doc §4.2, mirroring frontend-mock's
    visibleKps())."""
    kb = _create_kb(client, "kb-list-no-answers")
    kp = _create_kp(client, kb["id"], "kp-no-answers-yet")

    resp = client.get(_list_url(kb["id"]))
    row = next(r for r in resp.json()["data"] if r["id"] == kp["id"])
    assert row["resolved"]["status"] == "none"


def test_list_at_parameter_affects_each_row_independently(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb, kp = _seed_refund_policy_kp(client, db_engine)
    resp = client.get(_list_url(kb["id"]), params={"at": "2026-07-25"})
    row = next(r for r in resp.json()["data"] if r["id"] == kp["id"])
    assert row["resolved"]["status"] == "none"
