"""Integration tests for GET /knowledge-bases/{kb_id}/stats (issue #12).
See docs/specs/2026-08-09-change-log-and-kb-stats-api-design.md §4.5.
"""
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _create_kb(client: TestClient, name: str) -> dict:
    return client.post("/knowledge-bases", json={"name": name}).json()["data"]


def _create_kp(client: TestClient, kb_id: int, title: str) -> dict:
    return client.post(f"/knowledge-bases/{kb_id}/knowledge-points", json={"title": title}).json()["data"]


def _write_answer(client: TestClient, kb_id: int, kp_id: int, content: str, effective_time: str) -> dict:
    return client.post(
        f"/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answers",
        json={"content": content, "effective_time": effective_time},
    ).json()["data"]


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


def _stats_url(kb_id: int) -> str:
    return f"/knowledge-bases/{kb_id}/stats"


def test_empty_knowledge_base_has_all_zero_stats(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-stats-empty")
    resp = client.get(_stats_url(kb["id"]))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data == {
        "subject_count": 0,
        "active_answer_count": 0,
        "enabled_dimension_count": 0,
        "today_change_count": 0,
    }


def test_subject_count_excludes_deleted_knowledge_points(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-stats-subject")
    _create_kp(client, kb["id"], "kp-active-1")
    _create_kp(client, kb["id"], "kp-active-2")
    kp_deleted = _create_kp(client, kb["id"], "kp-to-delete")
    client.post(
        f"/knowledge-bases/{kb['id']}/knowledge-points/{kp_deleted['id']}/delete", json={"delete_reason": "x"}
    )

    data = client.get(_stats_url(kb["id"])).json()["data"]
    assert data["subject_count"] == 2


def test_active_answer_count_excludes_answers_under_a_deleted_knowledge_point(
    client: TestClient, migrated_schema
) -> None:
    """Regression for design doc §4.5's core scenario: an un-revoked answer
    under a soft-deleted knowledge point must not count as "在用",
    even though Answer.revoked is still False on it — filtering by
    Answer.revoked alone is not enough."""
    kb = _create_kb(client, "kb-stats-active-answers")
    kp_active = _create_kp(client, kb["id"], "kp-active")
    kp_deleted = _create_kp(client, kb["id"], "kp-deleted")
    _write_answer(client, kb["id"], kp_active["id"], "content", str(date.today()))
    _write_answer(client, kb["id"], kp_deleted["id"], "content", str(date.today()))

    client.post(
        f"/knowledge-bases/{kb['id']}/knowledge-points/{kp_deleted['id']}/delete", json={"delete_reason": "x"}
    )

    data = client.get(_stats_url(kb["id"])).json()["data"]
    assert data["active_answer_count"] == 1


def test_active_answer_count_decreases_after_revoke(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-stats-revoke")
    kp = _create_kp(client, kb["id"], "kp-stats-revoke")
    answer = _write_answer(client, kb["id"], kp["id"], "content", str(date.today()))

    assert client.get(_stats_url(kb["id"])).json()["data"]["active_answer_count"] == 1

    client.post(
        f"/knowledge-bases/{kb['id']}/knowledge-points/{kp['id']}/answers/{answer['id']}/revoke",
        json={"revoke_reason": "x"},
    )

    assert client.get(_stats_url(kb["id"])).json()["data"]["active_answer_count"] == 0


def test_enabled_dimension_count_reflects_activate_deactivate(client: TestClient, migrated_schema, db_engine) -> None:
    kb = _create_kb(client, "kb-stats-dims")
    assert client.get(_stats_url(kb["id"])).json()["data"]["enabled_dimension_count"] == 0

    _enable_dimension(db_engine, kb["id"], "tenant", "租户")
    assert client.get(_stats_url(kb["id"])).json()["data"]["enabled_dimension_count"] == 1

    client.post("/dimensions/tenant/deactivate")
    assert client.get(_stats_url(kb["id"])).json()["data"]["enabled_dimension_count"] == 0


def test_today_change_count_counts_created_and_revoked_today_without_double_counting(
    client: TestClient, migrated_schema
) -> None:
    """Regression for design doc §4.5's 'by row, not by event' rule: an
    answer created AND revoked on the same day must count once, not
    twice."""
    kb = _create_kb(client, "kb-stats-today")
    kp1 = _create_kp(client, kb["id"], "kp-stats-today-1")
    kp2 = _create_kp(client, kb["id"], "kp-stats-today-2")

    a1 = _write_answer(client, kb["id"], kp1["id"], "content-1", str(date.today()))
    assert client.get(_stats_url(kb["id"])).json()["data"]["today_change_count"] == 1

    client.post(
        f"/knowledge-bases/{kb['id']}/knowledge-points/{kp1['id']}/answers/{a1['id']}/revoke",
        json={"revoke_reason": "x"},
    )
    # created today AND revoked today -> still counts once, not twice
    assert client.get(_stats_url(kb["id"])).json()["data"]["today_change_count"] == 1

    # A second, unrelated answer (different knowledge point, so it isn't
    # blocked by the "can't write into an already-revoked chain" guard)
    # created today must add a second, independent count.
    _write_answer(client, kb["id"], kp2["id"], "content-2", str(date.today()))
    assert client.get(_stats_url(kb["id"])).json()["data"]["today_change_count"] == 2


def test_stats_nonexistent_kb_returns_404(client: TestClient, migrated_schema) -> None:
    resp = client.get(_stats_url(999999))
    assert resp.status_code == 404
