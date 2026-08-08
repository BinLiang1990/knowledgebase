"""Tests for the dimension-management write APIs (issue #9):
POST/PATCH/activate/deactivate on /dimensions, GET /admin/dimensions, and
PUT /knowledge-bases/{kb_id}/enabled-dimensions. See
docs/specs/2026-08-08-dimension-management-api-design.md.
"""
from fastapi.testclient import TestClient


def _create_kb(client: TestClient, name: str) -> dict:
    return client.post("/knowledge-bases", json={"name": name}).json()["data"]


def _create_kp(client: TestClient, kb_id: int, title: str) -> dict:
    return client.post(f"/knowledge-bases/{kb_id}/knowledge-points", json={"title": title}).json()["data"]


def _write_answer(client: TestClient, kb_id: int, kp_id: int, coord: dict, content: str = "content") -> dict:
    return client.post(
        f"/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answers",
        json={"content": content, "effective_time": "2026-08-01", "coord": coord},
    ).json()["data"]


# ---------------------------------------------------------------- create ---


def test_create_dimension_success(client: TestClient, migrated_schema) -> None:
    resp = client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["key"] == "地区"
    assert data["label"] == "地区"
    assert data["field_type"] == "text"
    assert data["weight"] == 50
    assert data["default_value"] is None
    assert data["status"] == "active"
    assert data["answer_count"] == 0


def test_create_dimension_with_weight_and_default_value(client: TestClient, migrated_schema) -> None:
    resp = client.post(
        "/dimensions", json={"label": "优先级", "field_type": "number", "weight": 90, "default_value": "1"}
    )
    data = resp.json()["data"]
    assert data["weight"] == 90
    assert data["default_value"] == "1"


def test_create_dimension_duplicate_key_is_rejected(client: TestClient, migrated_schema) -> None:
    client.post("/dimensions", json={"label": "租户", "field_type": "text"})
    resp = client.post("/dimensions", json={"label": "租户", "field_type": "text"})
    assert resp.status_code == 400
    assert resp.json()["code"] == 444


def test_create_dimension_duplicate_key_is_case_and_accent_insensitive(
    client: TestClient, migrated_schema
) -> None:
    """dimension_definition.key uses the same utf8mb4_0900_ai_ci collation as
    knowledge_base.name (issue #1) — "Region" and "region" collide as
    duplicates. Design doc §4.1 — locked in by this test, not left as an
    assumption."""
    client.post("/dimensions", json={"label": "Region", "field_type": "text"})
    resp = client.post("/dimensions", json={"label": "region", "field_type": "text"})
    assert resp.status_code == 400


def test_create_dimension_label_over_100_chars_is_rejected(client: TestClient, migrated_schema) -> None:
    resp = client.post("/dimensions", json={"label": "a" * 101, "field_type": "text"})
    assert resp.status_code == 422


def test_create_dimension_blank_label_is_rejected(client: TestClient, migrated_schema) -> None:
    resp = client.post("/dimensions", json={"label": "   ", "field_type": "text"})
    assert resp.status_code == 422


def test_create_dimension_label_containing_slash_is_rejected(client: TestClient, migrated_schema) -> None:
    """A "/" in the value that becomes `key` would make it unreachable by
    PATCH/activate/deactivate's single {key} path segment afterwards —
    Starlette decodes a percent-encoded "%2F" back to "/" before routing,
    so no client-side encoding trick can address it. Codex outer-gate
    finding on PR #25."""
    resp = client.post("/dimensions", json={"label": "sales/region", "field_type": "text"})
    assert resp.status_code == 422


def test_create_dimension_weight_out_of_range_is_rejected(client: TestClient, migrated_schema) -> None:
    assert client.post("/dimensions", json={"label": "a", "field_type": "text", "weight": 0}).status_code == 422
    assert client.post("/dimensions", json={"label": "b", "field_type": "text", "weight": 101}).status_code == 422


# ---------------------------------------------------------------- update ---


def test_update_dimension_label_weight_default_value(client: TestClient, migrated_schema) -> None:
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    resp = client.patch("/dimensions/地区", json={"label": "地域", "weight": 80, "default_value": "华东"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["key"] == "地区"  # key never changes
    assert data["label"] == "地域"
    assert data["weight"] == 80
    assert data["default_value"] == "华东"


def test_update_dimension_cannot_change_field_type(client: TestClient, migrated_schema) -> None:
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    resp = client.patch("/dimensions/地区", json={"label": "地区", "field_type": "number"})
    assert resp.status_code == 200
    # field_type isn't a field DimensionUpdate even accepts — the extra key
    # in the request body is silently dropped, not applied.
    assert resp.json()["data"]["field_type"] == "text"


def test_update_dimension_default_value_can_be_cleared(client: TestClient, migrated_schema) -> None:
    client.post("/dimensions", json={"label": "地区", "field_type": "text", "default_value": "华东"})
    resp = client.patch("/dimensions/地区", json={"default_value": None})
    assert resp.json()["data"]["default_value"] is None


def test_update_dimension_omitting_default_value_keeps_it_unchanged(client: TestClient, migrated_schema) -> None:
    client.post("/dimensions", json={"label": "地区", "field_type": "text", "default_value": "华东"})
    resp = client.patch("/dimensions/地区", json={"weight": 60})
    assert resp.json()["data"]["default_value"] == "华东"


def test_update_nonexistent_dimension_returns_404(client: TestClient, migrated_schema) -> None:
    resp = client.patch("/dimensions/does-not-exist", json={"weight": 60})
    assert resp.status_code == 404


def test_update_dimension_reflects_real_answer_count_not_zero(client: TestClient, migrated_schema) -> None:
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    kb = _create_kb(client, "kb-dim-update-count")
    client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": ["地区"]})
    kp = _create_kp(client, kb["id"], "kp-1")
    _write_answer(client, kb["id"], kp["id"], {"地区": "华东"})

    resp = client.patch("/dimensions/地区", json={"weight": 60})
    assert resp.json()["data"]["answer_count"] == 1


# -------------------------------------------------------- activate/deactivate ---


def test_deactivate_then_activate_dimension(client: TestClient, migrated_schema) -> None:
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    resp = client.post("/dimensions/地区/deactivate")
    assert resp.json()["data"]["status"] == "deprecated"
    resp = client.post("/dimensions/地区/activate")
    assert resp.json()["data"]["status"] == "active"


def test_deactivated_dimension_excluded_from_public_list_but_visible_in_admin(
    client: TestClient, migrated_schema
) -> None:
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    client.post("/dimensions/地区/deactivate")

    public_keys = {row["key"] for row in client.get("/dimensions").json()["data"]}
    assert "地区" not in public_keys

    admin_keys = {row["key"] for row in client.get("/admin/dimensions").json()["data"]}
    assert "地区" in admin_keys


def test_deactivate_nonexistent_dimension_returns_404(client: TestClient, migrated_schema) -> None:
    assert client.post("/dimensions/does-not-exist/deactivate").status_code == 404


def test_deactivating_dimension_does_not_affect_existing_answer_values(
    client: TestClient, migrated_schema
) -> None:
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    kb = _create_kb(client, "kb-dim-deactivate")
    client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": ["地区"]})
    kp = _create_kp(client, kb["id"], "kp-1")
    _write_answer(client, kb["id"], kp["id"], {"地区": "华东"})

    client.post("/dimensions/地区/deactivate")

    resp = client.get(f"/knowledge-bases/{kb['id']}/knowledge-points/{kp['id']}/answer-groups")
    groups = resp.json()["data"]
    assert any(g["coord"] == {"地区": "华东"} for g in groups)


# ------------------------------------------------------------- admin list ---


def test_admin_list_returns_all_statuses(client: TestClient, migrated_schema) -> None:
    client.post("/dimensions", json={"label": "启用中", "field_type": "text"})
    client.post("/dimensions", json={"label": "已停用", "field_type": "text"})
    client.post("/dimensions/已停用/deactivate")

    rows = client.get("/admin/dimensions").json()["data"]
    by_key = {row["key"]: row for row in rows}
    assert by_key["启用中"]["status"] == "active"
    assert by_key["已停用"]["status"] == "deprecated"


def test_admin_list_answer_count_only_counts_non_revoked(client: TestClient, migrated_schema) -> None:
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    kb = _create_kb(client, "kb-dim-admin-count")
    client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": ["地区"]})
    kp = _create_kp(client, kb["id"], "kp-1")
    a1 = _write_answer(client, kb["id"], kp["id"], {"地区": "华东"})
    _write_answer(client, kb["id"], kp["id"], {"地区": "华南"})
    # Migrate a1's condition away, revoking its whole chain (地区=华东).
    client.post(
        f"/knowledge-bases/{kb['id']}/knowledge-points/{kp['id']}/answers/{a1['id']}/edit",
        json={"content": "moved", "effective_time": "2026-08-01", "coord": {"地区": "华北"}, "migration_reason": "x"},
    )

    rows = client.get("/admin/dimensions").json()["data"]
    row = next(r for r in rows if r["key"] == "地区")
    # 华南 (live) + 华北 (live, migrated target) = 2; 华东's whole chain is
    # now revoked and must not count.
    assert row["answer_count"] == 2


def test_admin_list_dimension_keyed_admin_still_routes_to_the_admin_list(
    client: TestClient, migrated_schema
) -> None:
    """Regression test for design doc §4.6: a dimension whose key happens to
    be the literal string "admin" must not make GET /admin/dimensions
    ambiguous with any future /dimensions/{key}-shaped route."""
    client.post("/dimensions", json={"label": "admin", "field_type": "text"})
    resp = client.get("/admin/dimensions")
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)
    assert any(row["key"] == "admin" for row in resp.json()["data"])


# ------------------------------------------------------ enabled-dimensions ---


def test_set_enabled_dimensions_success(client: TestClient, migrated_schema) -> None:
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    client.post("/dimensions", json={"label": "优先级", "field_type": "number"})
    kb = _create_kb(client, "kb-set-dims")

    resp = client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": ["地区", "优先级"]})
    assert resp.status_code == 200
    keys = {row["key"] for row in resp.json()["data"]}
    assert keys == {"地区", "优先级"}

    # And it persists — a fresh GET agrees.
    assert {row["key"] for row in client.get(f"/knowledge-bases/{kb['id']}/enabled-dimensions").json()["data"]} == keys


def test_set_enabled_dimensions_replaces_not_merges(client: TestClient, migrated_schema) -> None:
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    client.post("/dimensions", json={"label": "优先级", "field_type": "number"})
    kb = _create_kb(client, "kb-replace-dims")
    client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": ["地区"]})

    resp = client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": ["优先级"]})
    keys = {row["key"] for row in resp.json()["data"]}
    assert keys == {"优先级"}  # 地区 is gone, not merged in


def test_set_enabled_dimensions_empty_list_clears_all(client: TestClient, migrated_schema) -> None:
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    kb = _create_kb(client, "kb-clear-dims")
    client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": ["地区"]})

    resp = client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": []})
    assert resp.json()["data"] == []


def test_set_enabled_dimensions_dedupes_repeated_keys(client: TestClient, migrated_schema) -> None:
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    kb = _create_kb(client, "kb-dedupe-dims")

    resp = client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": ["地区", "地区"]})
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1


def test_set_enabled_dimensions_nonexistent_key_is_rejected(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-bad-dims")
    resp = client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": ["no-such-dim"]})
    assert resp.status_code == 400


def test_set_enabled_dimensions_deprecated_key_is_rejected(client: TestClient, migrated_schema) -> None:
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    client.post("/dimensions/地区/deactivate")
    kb = _create_kb(client, "kb-deprecated-dims")

    resp = client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": ["地区"]})
    assert resp.status_code == 400


def test_set_enabled_dimensions_a_bad_key_rejects_the_whole_request(client: TestClient, migrated_schema) -> None:
    """One invalid key in the batch must not partially apply the rest."""
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    kb = _create_kb(client, "kb-partial-dims")

    resp = client.put(
        f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": ["地区", "no-such-dim"]}
    )
    assert resp.status_code == 400
    assert client.get(f"/knowledge-bases/{kb['id']}/enabled-dimensions").json()["data"] == []


def test_set_enabled_dimensions_nonexistent_kb_returns_404(client: TestClient, migrated_schema) -> None:
    resp = client.put("/knowledge-bases/999999999/enabled-dimensions", json={"dimension_keys": []})
    assert resp.status_code == 404


def test_set_enabled_dimensions_omitted_field_is_rejected_not_defaulted_to_empty(
    client: TestClient, migrated_schema
) -> None:
    """An explicit `[]` is how "clear everything" is spelled — an omitted
    field or a misspelled key name must 422, not silently behave like that
    same empty list and wipe every enabled dimension for the KB. Codex
    outer-gate finding on PR #25."""
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    kb = _create_kb(client, "kb-missing-field-dims")
    client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": ["地区"]})

    resp = client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={})
    assert resp.status_code == 422
    # And the previously-saved enabled set must be untouched by the
    # rejected request.
    assert len(client.get(f"/knowledge-bases/{kb['id']}/enabled-dimensions").json()["data"]) == 1


def test_set_enabled_dimensions_preserves_link_to_a_since_deprecated_dimension(
    client: TestClient, migrated_schema
) -> None:
    """A dimension enabled for this KB, then globally deprecated by an
    unrelated admin action, disappears from _enabled_dimensions()'s
    filtered view — the settings UI this endpoint backs can never show it
    as a checkbox, so no resubmission can ever include it. Saving other
    changes must not delete its retained join-table row: reactivating the
    dimension later should make it show up as still-enabled for this KB,
    exactly as PRD §4.3 promises for a KB-level "取消启用不影响..." case
    applied to the deprecation side. Codex outer-gate finding on PR #25."""
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    client.post("/dimensions", json={"label": "优先级", "field_type": "number"})
    kb = _create_kb(client, "kb-preserve-deprecated-dim")
    client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": ["地区", "优先级"]})

    client.post("/dimensions/地区/deactivate")
    # The admin now only sees "优先级" in the settings UI (地区 is hidden)
    # and saves with just that — must not wipe 地区's retained link.
    resp = client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": ["优先级"]})
    assert {row["key"] for row in resp.json()["data"]} == {"优先级"}

    client.post("/dimensions/地区/activate")
    keys_after_reactivate = {row["key"] for row in client.get(f"/knowledge-bases/{kb['id']}/enabled-dimensions").json()["data"]}
    assert keys_after_reactivate == {"地区", "优先级"}


def test_disabling_dimension_for_kb_does_not_affect_existing_answer_values(
    client: TestClient, migrated_schema
) -> None:
    client.post("/dimensions", json={"label": "地区", "field_type": "text"})
    kb = _create_kb(client, "kb-disable-dim")
    client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": ["地区"]})
    kp = _create_kp(client, kb["id"], "kp-1")
    _write_answer(client, kb["id"], kp["id"], {"地区": "华东"})

    client.put(f"/knowledge-bases/{kb['id']}/enabled-dimensions", json={"dimension_keys": []})

    resp = client.get(f"/knowledge-bases/{kb['id']}/knowledge-points/{kp['id']}/answer-groups")
    groups = resp.json()["data"]
    assert any(g["coord"] == {"地区": "华东"} for g in groups)
