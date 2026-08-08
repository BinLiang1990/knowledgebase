"""Tests for POST .../answers/{id}/promote-to-default and .../revoke
(issue #10). See docs/specs/2026-08-08-answer-promote-revoke-api-design.md.
"""
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _create_kb(client: TestClient, name: str) -> dict:
    return client.post("/knowledge-bases", json={"name": name}).json()["data"]


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


def _create_kp(client: TestClient, kb_id: int, title: str) -> dict:
    return client.post(f"/knowledge-bases/{kb_id}/knowledge-points", json={"title": title}).json()["data"]


def _answers_url(kb_id: int, kp_id: int) -> str:
    return f"/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answers"


def _write_answer(
    client: TestClient, kb_id: int, kp_id: int, content: str, effective_time: str, coord: dict | None = None
) -> dict:
    payload = {"content": content, "effective_time": effective_time}
    if coord is not None:
        payload["coord"] = coord
    return client.post(_answers_url(kb_id, kp_id), json=payload).json()["data"]


def _promote_url(kb_id: int, kp_id: int, answer_id: int) -> str:
    return f"{_answers_url(kb_id, kp_id)}/{answer_id}/promote-to-default"


def _revoke_url(kb_id: int, kp_id: int, answer_id: int) -> str:
    return f"{_answers_url(kb_id, kp_id)}/{answer_id}/revoke"


def _groups(client: TestClient, kb_id: int, kp_id: int) -> list[dict]:
    return client.get(f"/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answer-groups").json()["data"]


# ---------------------------------------------------------- promote-to-default ---


def test_promote_to_default_creates_a_new_default_version_with_source_content(
    client: TestClient, migrated_schema
) -> None:
    kb = _create_kb(client, "kb-promote-basic")
    kp = _create_kp(client, kb["id"], "kp-1")
    source = _write_answer(client, kb["id"], kp["id"], "acme content", "2026-08-01")
    resp = client.post(_promote_url(kb["id"], kp["id"], source["id"]), json={"effective_time": "2026-08-05"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["coord"] == {}
    assert data["content"] == "acme content"
    assert data["effective_time"] == "2026-08-05"
    assert data["operator"] == "admin"
    assert data["source"] == "人工填报"
    assert data["id"] != source["id"]


def test_promote_to_default_accepts_optional_note(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-promote-note")
    kp = _create_kp(client, kb["id"], "kp-1")
    source = _write_answer(client, kb["id"], kp["id"], "content", "2026-08-01")

    resp = client.post(_promote_url(kb["id"], kp["id"], source["id"]), json={"effective_time": "2026-08-05", "note": "手动设为默认"})
    assert resp.json()["data"]["note"] == "手动设为默认"

    resp2 = client.post(_promote_url(kb["id"], kp["id"], source["id"]), json={"effective_time": "2026-08-06"})
    assert resp2.json()["data"]["note"] is None


def test_promote_to_default_does_not_affect_the_source_answer(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create_kb(client, "kb-promote-source-unaffected")
    _enable_dimension(db_engine, kb["id"], "tenant", "租户")
    kp = _create_kp(client, kb["id"], "kp-1")
    # A source with a non-empty coord — promoting copies its content into
    # the *separate* default (coord={}) group, leaving this group intact.
    # A default-coord source would land back in the same group it came
    # from, which isn't what this test means to exercise.
    source = _write_answer(client, kb["id"], kp["id"], "acme content", "2026-08-01", coord={"tenant": "acme"})

    client.post(_promote_url(kb["id"], kp["id"], source["id"]), json={"effective_time": "2026-08-05"})

    groups = _groups(client, kb["id"], kp["id"])
    source_group = next(g for g in groups if g["coord"] == {"tenant": "acme"})
    assert source_group["latest_answer"]["content"] == "acme content"
    assert source_group["latest_answer"]["id"] == source["id"]
    assert source_group["revoked"] is False
    assert source_group["revoked"] is False


def test_promote_to_default_rejects_when_knowledge_point_is_deleted(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-promote-deleted-kp")
    kp = _create_kp(client, kb["id"], "kp-1")
    source = _write_answer(client, kb["id"], kp["id"], "content", "2026-08-01")
    client.post(f"/knowledge-bases/{kb['id']}/knowledge-points/{kp['id']}/delete", json={"delete_reason": "x"})

    resp = client.post(_promote_url(kb["id"], kp["id"], source["id"]), json={"effective_time": "2026-08-05"})
    assert resp.status_code == 400


def test_promote_to_default_rejects_when_default_chain_is_revoked(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-promote-revoked-default")
    kp = _create_kp(client, kb["id"], "kp-1")
    default_answer = _write_answer(client, kb["id"], kp["id"], "default content", "2026-08-01")
    other_source = _write_answer(client, kb["id"], kp["id"], "other content", "2026-08-01")
    client.post(_revoke_url(kb["id"], kp["id"], default_answer["id"]), json={"revoke_reason": "x"})

    resp = client.post(_promote_url(kb["id"], kp["id"], other_source["id"]), json={"effective_time": "2026-08-05"})
    assert resp.status_code == 400


def test_promote_to_default_source_not_found_returns_404(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-promote-404")
    kp = _create_kp(client, kb["id"], "kp-1")
    resp = client.post(_promote_url(kb["id"], kp["id"], 999999999), json={"effective_time": "2026-08-05"})
    assert resp.status_code == 404


def test_promote_to_default_rejects_an_answer_id_from_a_different_knowledge_point(
    client: TestClient, migrated_schema
) -> None:
    kb = _create_kb(client, "kb-promote-cross-kp")
    kp_a = _create_kp(client, kb["id"], "kp-a")
    kp_b = _create_kp(client, kb["id"], "kp-b")
    answer_in_a = _write_answer(client, kb["id"], kp_a["id"], "content", "2026-08-01")

    resp = client.post(_promote_url(kb["id"], kp_b["id"], answer_in_a["id"]), json={"effective_time": "2026-08-05"})
    assert resp.status_code == 404


def test_promote_to_default_can_copy_content_from_an_already_revoked_source(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    """§4.3: promoting copies *text*, it doesn't resurrect the source
    chain — a previously-correct, since-revoked answer's wording can still
    be reused. Uses a non-default source so revoking it doesn't also
    revoke the (separate) default chain this promotion writes into."""
    kb = _create_kb(client, "kb-promote-from-revoked-source")
    _enable_dimension(db_engine, kb["id"], "tenant", "租户")
    kp = _create_kp(client, kb["id"], "kp-1")
    source = _write_answer(client, kb["id"], kp["id"], "still-good wording", "2026-08-01", coord={"tenant": "acme"})
    client.post(_revoke_url(kb["id"], kp["id"], source["id"]), json={"revoke_reason": "condition retired"})

    resp = client.post(_promote_url(kb["id"], kp["id"], source["id"]), json={"effective_time": "2026-08-05"})
    assert resp.status_code == 200
    assert resp.json()["data"]["content"] == "still-good wording"


# --------------------------------------------------------------------- revoke ---


def test_revoke_marks_the_whole_chain_revoked_not_just_the_targeted_row(
    client: TestClient, migrated_schema
) -> None:
    kb = _create_kb(client, "kb-revoke-chain")
    kp = _create_kp(client, kb["id"], "kp-1")
    v1 = _write_answer(client, kb["id"], kp["id"], "v1", "2026-08-01")
    v2 = _write_answer(client, kb["id"], kp["id"], "v2", "2026-08-02")

    resp = client.post(_revoke_url(kb["id"], kp["id"], v2["id"]), json={"revoke_reason": "wrong"})
    assert resp.status_code == 200
    assert resp.json()["data"]["revoked"] is True

    groups = _groups(client, kb["id"], kp["id"])
    group = next(g for g in groups if g["latest_answer"]["id"] == v2["id"])
    assert group["revoked"] is True
    assert group["live_answer"] is None
    assert group["version_count"] == 2  # v1 stays a permanent, readable version


def test_revoke_requires_a_non_blank_reason(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-revoke-blank-reason")
    kp = _create_kp(client, kb["id"], "kp-1")
    answer = _write_answer(client, kb["id"], kp["id"], "content", "2026-08-01")

    resp = client.post(_revoke_url(kb["id"], kp["id"], answer["id"]), json={"revoke_reason": "   "})
    assert resp.status_code == 422


def test_revoke_reason_over_500_chars_is_rejected(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-revoke-long-reason")
    kp = _create_kp(client, kb["id"], "kp-1")
    answer = _write_answer(client, kb["id"], kp["id"], "content", "2026-08-01")

    resp = client.post(_revoke_url(kb["id"], kp["id"], answer["id"]), json={"revoke_reason": "a" * 501})
    assert resp.status_code == 422


def test_revoke_then_resolve_no_longer_returns_the_revoked_answer(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-revoke-resolve")
    kp = _create_kp(client, kb["id"], "kp-1")
    answer = _write_answer(client, kb["id"], kp["id"], "content", "2026-08-01")
    client.post(_revoke_url(kb["id"], kp["id"], answer["id"]), json={"revoke_reason": "x"})

    resp = client.get(f"/knowledge-bases/{kb['id']}/knowledge-points/{kp['id']}/resolve")
    assert resp.json()["data"]["status"] == "none"


def test_revoke_then_answer_groups_still_shows_the_revoked_group_with_full_history(
    client: TestClient, migrated_schema
) -> None:
    kb = _create_kb(client, "kb-revoke-history")
    kp = _create_kp(client, kb["id"], "kp-1")
    v1 = _write_answer(client, kb["id"], kp["id"], "v1", "2026-08-01")
    client.post(_revoke_url(kb["id"], kp["id"], v1["id"]), json={"revoke_reason": "obsolete"})

    groups = _groups(client, kb["id"], kp["id"])
    assert len(groups) == 1
    assert groups[0]["revoked"] is True
    assert groups[0]["latest_answer"]["content"] == "v1"
    assert groups[0]["latest_answer"]["revoke_reason"] == "obsolete"


def test_revoke_is_idempotent_and_keeps_the_original_reason(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-revoke-idempotent")
    kp = _create_kp(client, kb["id"], "kp-1")
    answer = _write_answer(client, kb["id"], kp["id"], "content", "2026-08-01")

    first = client.post(_revoke_url(kb["id"], kp["id"], answer["id"]), json={"revoke_reason": "first reason"})
    assert first.json()["data"]["revoke_reason"] == "first reason"

    second = client.post(_revoke_url(kb["id"], kp["id"], answer["id"]), json={"revoke_reason": "retry reason"})
    assert second.status_code == 200
    assert second.json()["data"]["revoke_reason"] == "first reason"
    assert second.json()["data"]["revoked_at"] == first.json()["data"]["revoked_at"]
    assert second.json()["data"]["revoked_by"] == first.json()["data"]["revoked_by"]


def test_revoke_succeeds_even_when_the_knowledge_point_is_deleted(client: TestClient, migrated_schema) -> None:
    """PRD §6 rule #8: KP soft-delete and answer revocation are independent
    — unlike promote-to-default (§4.4), revoke must not be blocked here."""
    kb = _create_kb(client, "kb-revoke-deleted-kp")
    kp = _create_kp(client, kb["id"], "kp-1")
    answer = _write_answer(client, kb["id"], kp["id"], "content", "2026-08-01")
    client.post(f"/knowledge-bases/{kb['id']}/knowledge-points/{kp['id']}/delete", json={"delete_reason": "x"})

    resp = client.post(_revoke_url(kb["id"], kp["id"], answer["id"]), json={"revoke_reason": "x"})
    assert resp.status_code == 200
    assert resp.json()["data"]["revoked"] is True


def test_revoke_answer_not_found_returns_404(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-revoke-404")
    kp = _create_kp(client, kb["id"], "kp-1")
    resp = client.post(_revoke_url(kb["id"], kp["id"], 999999999), json={"revoke_reason": "x"})
    assert resp.status_code == 404


def test_revoke_rejects_an_answer_id_from_a_different_knowledge_point(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-revoke-cross-kp")
    kp_a = _create_kp(client, kb["id"], "kp-a")
    kp_b = _create_kp(client, kb["id"], "kp-b")
    answer_in_a = _write_answer(client, kb["id"], kp_a["id"], "content", "2026-08-01")

    resp = client.post(_revoke_url(kb["id"], kp_b["id"], answer_in_a["id"]), json={"revoke_reason": "x"})
    assert resp.status_code == 404


def test_revoke_does_not_affect_a_different_knowledge_points_chain_sharing_the_same_coord_hash(
    client: TestClient, migrated_schema
) -> None:
    """Regression test for the exact bug adversarial review caught before
    any code was written (design doc §3/§6): compute_coord_hash({}) is the
    same value for every knowledge point, since it's a pure function of
    the coord dict alone. Revoking KP-A's default chain must never touch
    KP-B's, even though both share that identical hash."""
    kb = _create_kb(client, "kb-revoke-isolation")
    kp_a = _create_kp(client, kb["id"], "kp-a")
    kp_b = _create_kp(client, kb["id"], "kp-b")
    answer_a = _write_answer(client, kb["id"], kp_a["id"], "content a", "2026-08-01")
    answer_b = _write_answer(client, kb["id"], kp_b["id"], "content b", "2026-08-01")
    assert answer_a["coord_hash"] == answer_b["coord_hash"]  # both coord={}

    client.post(_revoke_url(kb["id"], kp_a["id"], answer_a["id"]), json={"revoke_reason": "x"})

    groups_b = _groups(client, kb["id"], kp_b["id"])
    assert groups_b[0]["revoked"] is False
    assert groups_b[0]["live_answer"] is not None
    assert groups_b[0]["live_answer"]["content"] == "content b"
