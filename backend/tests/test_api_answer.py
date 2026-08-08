from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _create_kb(client: TestClient, name: str) -> dict:
    return client.post("/knowledge-bases", json={"name": name}).json()["data"]


def _create_kp(client: TestClient, kb_id: int, title: str) -> dict:
    return client.post(f"/knowledge-bases/{kb_id}/knowledge-points", json={"title": title}).json()["data"]


def _enable_dimension(db_engine: Engine, kb_id: int, key: str, label: str, field_type: str = "text") -> None:
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO dimension_definition (`key`, label, field_type) VALUES (:key, :label, :ft)"
            ),
            {"key": key, "label": label, "ft": field_type},
        )
        conn.execute(
            text(
                "INSERT INTO knowledge_base_enabled_dimension (knowledge_base_id, dimension_key) "
                "VALUES (:kb, :key)"
            ),
            {"kb": kb_id, "key": key},
        )


def _answers_url(kb_id: int, kp_id: int) -> str:
    return f"/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answers"


def test_write_answer_with_no_coord_creates_default_answer(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-answer-default")
    kp = _create_kp(client, kb["id"], "kp-answer-default")
    resp = client.post(_answers_url(kb["id"], kp["id"]), json={"content": "hello", "effective_time": "2026-08-08"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["coord"] == {}
    assert data["source"] == "人工填报"
    assert data["operator"] == "admin"
    assert data["revoked"] is False


def test_write_answer_with_enabled_dimension_succeeds(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create_kb(client, "kb-answer-dim")
    _enable_dimension(db_engine, kb["id"], "tenant", "租户")
    kp = _create_kp(client, kb["id"], "kp-answer-dim")

    resp = client.post(
        _answers_url(kb["id"], kp["id"]),
        json={"content": "tenant answer", "effective_time": "2026-08-08", "coord": {"tenant": "acme"}},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["coord"] == {"tenant": "acme"}


def test_write_answer_with_dimension_not_enabled_is_rejected(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-answer-not-enabled")
    kp = _create_kp(client, kb["id"], "kp-answer-not-enabled")
    resp = client.post(
        _answers_url(kb["id"], kp["id"]),
        json={"content": "x", "effective_time": "2026-08-08", "coord": {"tenant": "acme"}},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 444


def test_write_answer_with_invalid_number_value_is_rejected(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create_kb(client, "kb-answer-bad-number")
    _enable_dimension(db_engine, kb["id"], "priority", "优先级", field_type="number")
    kp = _create_kp(client, kb["id"], "kp-answer-bad-number")

    resp = client.post(
        _answers_url(kb["id"], kp["id"]),
        json={"content": "x", "effective_time": "2026-08-08", "coord": {"priority": "not-a-number"}},
    )
    assert resp.status_code == 400


def test_write_answer_with_invalid_date_value_is_rejected(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create_kb(client, "kb-answer-bad-date")
    _enable_dimension(db_engine, kb["id"], "valid_from", "生效日", field_type="date")
    kp = _create_kp(client, kb["id"], "kp-answer-bad-date")

    resp = client.post(
        _answers_url(kb["id"], kp["id"]),
        json={"content": "x", "effective_time": "2026-08-08", "coord": {"valid_from": "not-a-date"}},
    )
    assert resp.status_code == 400


def test_write_answer_with_invalid_boolean_value_is_rejected(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create_kb(client, "kb-answer-bad-bool")
    _enable_dimension(db_engine, kb["id"], "is_vip", "是否VIP", field_type="boolean")
    kp = _create_kp(client, kb["id"], "kp-answer-bad-bool")

    resp = client.post(
        _answers_url(kb["id"], kp["id"]),
        json={"content": "x", "effective_time": "2026-08-08", "coord": {"is_vip": "true"}},
    )
    assert resp.status_code == 400


def test_write_answer_on_deleted_knowledge_point_is_rejected(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-answer-deleted-kp")
    kp = _create_kp(client, kb["id"], "kp-deleted-for-answer")
    client.post(
        f"/knowledge-bases/{kb['id']}/knowledge-points/{kp['id']}/delete", json={"delete_reason": "x"}
    )
    resp = client.post(_answers_url(kb["id"], kp["id"]), json={"content": "x", "effective_time": "2026-08-08"})
    assert resp.status_code == 400


def test_same_coord_same_effective_time_multiple_answers_allowed_created_at_orders_them(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create_kb(client, "kb-answer-same-time")
    kp = _create_kp(client, kb["id"], "kp-answer-same-time")
    r1 = client.post(
        _answers_url(kb["id"], kp["id"]), json={"content": "first", "effective_time": "2026-08-08"}
    )
    r2 = client.post(
        _answers_url(kb["id"], kp["id"]), json={"content": "second", "effective_time": "2026-08-08"}
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT content, created_at FROM answer WHERE knowledge_point_id = :kp ORDER BY created_at"
            ),
            {"kp": kp["id"]},
        ).all()
    assert [r[0] for r in rows] == ["first", "second"]
    assert rows[1][1] > rows[0][1]


def _edit_url(kb_id: int, kp_id: int, answer_id: int) -> str:
    return f"/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answers/{answer_id}/edit"


def test_edit_answer_without_coord_change_appends_new_version_to_same_chain(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create_kb(client, "kb-edit-same-chain")
    kp = _create_kp(client, kb["id"], "kp-edit-same-chain")
    original = client.post(
        _answers_url(kb["id"], kp["id"]), json={"content": "v1", "effective_time": "2026-08-08"}
    ).json()["data"]

    resp = client.post(
        _edit_url(kb["id"], kp["id"], original["id"]),
        json={"content": "v2", "effective_time": "2026-08-09"},
    )
    assert resp.status_code == 200
    new_answer = resp.json()["data"]
    assert new_answer["coord_hash"] == original["coord_hash"]
    assert new_answer["source"] == "人工编辑"
    assert new_answer["id"] != original["id"]

    with db_engine.connect() as conn:
        original_row = conn.execute(
            text("SELECT revoked, content FROM answer WHERE id = :id"), {"id": original["id"]}
        ).one()
    assert original_row[0] == 0
    assert original_row[1] == "v1"


def test_edit_answer_appending_does_not_require_dimensions_still_enabled(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    """PRD §6 rule #7: dimension deactivation must not break appending to a
    chain that already used it."""
    kb = _create_kb(client, "kb-edit-dim-disabled")
    _enable_dimension(db_engine, kb["id"], "tenant", "租户")
    kp = _create_kp(client, kb["id"], "kp-edit-dim-disabled")
    original = client.post(
        _answers_url(kb["id"], kp["id"]),
        json={"content": "v1", "effective_time": "2026-08-08", "coord": {"tenant": "acme"}},
    ).json()["data"]

    with db_engine.begin() as conn:
        conn.execute(text("UPDATE dimension_definition SET status = 'deprecated' WHERE `key` = 'tenant'"))

    resp = client.post(
        _edit_url(kb["id"], kp["id"], original["id"]),
        json={"content": "v2", "effective_time": "2026-08-09"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["coord"] == {"tenant": "acme"}


def test_edit_answer_changing_coord_migrates_revokes_old_chain_and_creates_new_one(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create_kb(client, "kb-edit-migrate")
    _enable_dimension(db_engine, kb["id"], "tenant", "租户")
    kp = _create_kp(client, kb["id"], "kp-edit-migrate")

    v1 = client.post(
        _answers_url(kb["id"], kp["id"]),
        json={"content": "v1", "effective_time": "2026-08-08", "coord": {"tenant": "acme"}},
    ).json()["data"]
    v2 = client.post(
        _edit_url(kb["id"], kp["id"], v1["id"]),
        json={"content": "v2", "effective_time": "2026-08-09"},
    ).json()["data"]

    resp = client.post(
        _edit_url(kb["id"], kp["id"], v2["id"]),
        json={
            "content": "migrated content",
            "effective_time": "2026-08-10",
            "coord": {"tenant": "other"},
            "migration_reason": "条件填错了，改成 other 租户",
        },
    )
    assert resp.status_code == 200
    new_chain = resp.json()["data"]
    assert new_chain["coord"] == {"tenant": "other"}
    assert new_chain["coord_hash"] != v1["coord_hash"]

    with db_engine.connect() as conn:
        old_chain_rows = conn.execute(
            text(
                "SELECT id, revoked, revoke_reason FROM answer "
                "WHERE knowledge_point_id = :kp AND coord_hash = :hash"
            ),
            {"kp": kp["id"], "hash": v1["coord_hash"]},
        ).all()
    assert len(old_chain_rows) == 2
    assert {row[0] for row in old_chain_rows} == {v1["id"], v2["id"]}
    assert all(row[1] == 1 for row in old_chain_rows)
    assert all(row[2] == "条件填错了，改成 other 租户" for row in old_chain_rows)


def test_edit_answer_changing_coord_without_migration_reason_is_rejected(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create_kb(client, "kb-edit-migrate-no-reason")
    _enable_dimension(db_engine, kb["id"], "tenant", "租户")
    kp = _create_kp(client, kb["id"], "kp-edit-migrate-no-reason")
    v1 = client.post(
        _answers_url(kb["id"], kp["id"]),
        json={"content": "v1", "effective_time": "2026-08-08", "coord": {"tenant": "acme"}},
    ).json()["data"]

    resp = client.post(
        _edit_url(kb["id"], kp["id"], v1["id"]),
        json={"content": "v2", "effective_time": "2026-08-09", "coord": {"tenant": "other"}},
    )
    assert resp.status_code == 400


def test_edit_answer_via_older_non_latest_version_id_still_migrates_whole_chain(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create_kb(client, "kb-edit-via-old-id")
    kp = _create_kp(client, kb["id"], "kp-edit-via-old-id")
    v1 = client.post(
        _answers_url(kb["id"], kp["id"]), json={"content": "v1", "effective_time": "2026-08-08"}
    ).json()["data"]
    client.post(
        _edit_url(kb["id"], kp["id"], v1["id"]),
        json={"content": "v2", "effective_time": "2026-08-09"},
    )

    resp = client.post(
        _edit_url(kb["id"], kp["id"], v1["id"]),
        json={
            "content": "migrated via old id",
            "effective_time": "2026-08-10",
            "coord": {"whatever": "no-such-dim"},
            "migration_reason": "should still fail dimension check",
        },
    )
    # dimension not enabled -> still validated even though we edited via an
    # older row id, proving the router doesn't special-case "must be latest"
    assert resp.status_code == 400

    with db_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT revoked FROM answer WHERE knowledge_point_id = :kp"), {"kp": kp["id"]}
        ).all()
    assert all(r[0] == 0 for r in rows)


def test_edit_revoked_answer_is_rejected(client: TestClient, migrated_schema, db_engine: Engine) -> None:
    kb = _create_kb(client, "kb-edit-revoked")
    kp = _create_kp(client, kb["id"], "kp-edit-revoked")
    v1 = client.post(
        _answers_url(kb["id"], kp["id"]), json={"content": "v1", "effective_time": "2026-08-08"}
    ).json()["data"]
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE answer SET revoked = 1 WHERE id = :id"), {"id": v1["id"]})

    resp = client.post(
        _edit_url(kb["id"], kp["id"], v1["id"]),
        json={"content": "v2", "effective_time": "2026-08-09"},
    )
    assert resp.status_code == 400


def test_edit_answer_explicit_null_coord_is_rejected_with_422(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-edit-null-coord")
    kp = _create_kp(client, kb["id"], "kp-edit-null-coord")
    v1 = client.post(
        _answers_url(kb["id"], kp["id"]), json={"content": "v1", "effective_time": "2026-08-08"}
    ).json()["data"]

    resp = client.post(
        _edit_url(kb["id"], kp["id"], v1["id"]),
        json={"content": "v2", "effective_time": "2026-08-09", "coord": None},
    )
    assert resp.status_code == 422


def test_edit_answer_nonexistent_answer_id_returns_404(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-edit-404")
    kp = _create_kp(client, kb["id"], "kp-edit-404")
    resp = client.post(
        _edit_url(kb["id"], kp["id"], 999999999),
        json={"content": "x", "effective_time": "2026-08-08"},
    )
    assert resp.status_code == 404


def test_write_answer_into_revoked_chain_is_rejected(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    """Found by the Codex outer-gate review on PR #20 (round 2): writing a
    fresh non-revoked row under an already-revoked coord_hash would silently
    resurrect a dead chain, leaving it with mixed revocation states."""
    kb = _create_kb(client, "kb-answer-revoked-chain")
    kp = _create_kp(client, kb["id"], "kp-answer-revoked-chain")
    v1 = client.post(
        _answers_url(kb["id"], kp["id"]), json={"content": "v1", "effective_time": "2026-08-08"}
    ).json()["data"]
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE answer SET revoked = 1 WHERE id = :id"), {"id": v1["id"]})

    resp = client.post(
        _answers_url(kb["id"], kp["id"]), json={"content": "resurrection attempt", "effective_time": "2026-08-09"}
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 444


def test_edit_answer_migrating_into_a_revoked_chain_is_rejected(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create_kb(client, "kb-edit-migrate-into-revoked")
    _enable_dimension(db_engine, kb["id"], "tenant", "租户")
    kp = _create_kp(client, kb["id"], "kp-edit-migrate-into-revoked")

    dead = client.post(
        _answers_url(kb["id"], kp["id"]),
        json={"content": "dead chain", "effective_time": "2026-08-08", "coord": {"tenant": "dead"}},
    ).json()["data"]
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE answer SET revoked = 1 WHERE id = :id"), {"id": dead["id"]})

    live = client.post(
        _answers_url(kb["id"], kp["id"]),
        json={"content": "live chain", "effective_time": "2026-08-08", "coord": {"tenant": "live"}},
    ).json()["data"]

    resp = client.post(
        _edit_url(kb["id"], kp["id"], live["id"]),
        json={
            "content": "trying to migrate into dead chain",
            "effective_time": "2026-08-09",
            "coord": {"tenant": "dead"},
            "migration_reason": "should be rejected",
        },
    )
    assert resp.status_code == 400

    with db_engine.connect() as conn:
        live_row = conn.execute(text("SELECT revoked FROM answer WHERE id = :id"), {"id": live["id"]}).one()
    assert live_row[0] == 0


def test_write_answer_content_has_no_length_limit(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-answer-long-content")
    kp = _create_kp(client, kb["id"], "kp-answer-long-content")
    long_content = "x" * 20000
    resp = client.post(
        _answers_url(kb["id"], kp["id"]), json={"content": long_content, "effective_time": "2026-08-08"}
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]["content"]) == 20000


def test_write_answer_note_exceeding_text_column_limit_still_succeeds(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    """MySQL TEXT caps at 65,535 bytes; answer.note is LONGTEXT (migration
    0002) specifically so a note longer than that doesn't 500 at commit.
    Found by the Codex outer-gate review on PR #20 (round 5).

    Cleans up its own oversized row before returning: the shared
    migrated_schema fixture downgrades all the way to base on teardown,
    which passes back through migration 0002's downgrade (LONGTEXT -> TEXT)
    — narrowing the column while a >65KB row still exists would fail that
    ALTER and leave the database in a broken intermediate state that
    cascades into every subsequent test's own setup.
    """
    kb = _create_kb(client, "kb-answer-long-note")
    kp = _create_kp(client, kb["id"], "kp-answer-long-note")
    long_note = "n" * 100000
    resp = client.post(
        _answers_url(kb["id"], kp["id"]),
        json={"content": "x", "effective_time": "2026-08-08", "note": long_note},
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]["note"]) == 100000

    with db_engine.begin() as conn:
        conn.execute(text("UPDATE answer SET note = NULL WHERE id = :id"), {"id": resp.json()["data"]["id"]})
