from fastapi.testclient import TestClient


def _create_kb(client: TestClient, name: str) -> dict:
    return client.post("/knowledge-bases", json={"name": name}).json()["data"]


def _batch_url(kb_id: int) -> str:
    return f"/knowledge-bases/{kb_id}/knowledge-points/batch-import"


def _list_kps(client: TestClient, kb_id: int) -> list[dict]:
    return client.get(f"/knowledge-bases/{kb_id}/knowledge-points").json()["data"]


def test_batch_import_all_succeed_mixed_with_and_without_default_answer(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-batch-ok")
    resp = client.post(
        _batch_url(kb["id"]),
        json={
            "items": [
                {"title": "kp-a"},
                {
                    "title": "kp-b",
                    "default_answer": {"content": "answer-b", "effective_time": "2026-08-01"},
                },
                {"title": "kp-c"},
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["created_count"] == 3
    assert data["failed_count"] == 0
    assert len(data["results"]) == 3

    for i, title in enumerate(["kp-a", "kp-b", "kp-c"]):
        r = data["results"][i]
        assert r["index"] == i
        assert r["status"] == "created"
        assert r["title"] == title
        assert r["knowledge_point_id"] is not None
        assert r["reason"] is None

    titles = {kp["title"] for kp in _list_kps(client, kb["id"])}
    assert titles == {"kp-a", "kp-b", "kp-c"}


def test_batch_import_created_knowledge_point_matches_single_create_fields(
    client: TestClient, migrated_schema
) -> None:
    kb = _create_kb(client, "kb-batch-fields")
    resp = client.post(
        _batch_url(kb["id"]),
        json={"items": [{"title": "kp-x", "default_answer": {"content": "c", "effective_time": "2026-08-01"}}]},
    )
    kp_id = resp.json()["data"]["results"][0]["knowledge_point_id"]

    detail = client.get(f"/knowledge-bases/{kb['id']}/knowledge-points/{kp_id}").json()["data"]
    assert detail["operator"] == "admin"
    assert detail["status"] == "active"
    assert detail["active_answer_count"] == 1

    groups = client.get(f"/knowledge-bases/{kb['id']}/knowledge-points/{kp_id}/answer-groups").json()["data"]
    assert groups[0]["coord"] == {}
    assert groups[0]["live_answer"]["operator"] == "admin"
    assert groups[0]["live_answer"]["source"] == "人工填报"
    assert groups[0]["live_answer"]["content"] == "c"


def test_batch_import_duplicate_title_within_batch_fails_second_but_not_others(
    client: TestClient, migrated_schema
) -> None:
    kb = _create_kb(client, "kb-batch-dup-internal")
    resp = client.post(
        _batch_url(kb["id"]),
        json={"items": [{"title": "same"}, {"title": "same"}, {"title": "other"}]},
    )
    data = resp.json()["data"]
    assert data["created_count"] == 2
    assert data["failed_count"] == 1

    assert data["results"][0]["status"] == "created"
    assert data["results"][1]["status"] == "failed"
    assert data["results"][1]["reason"] == "知识点标题已存在，请使用其他标题"
    assert data["results"][1]["knowledge_point_id"] is None
    assert data["results"][2]["status"] == "created"

    titles = [kp["title"] for kp in _list_kps(client, kb["id"])]
    assert titles.count("same") == 1
    assert "other" in titles


def test_batch_import_duplicate_against_existing_knowledge_point_fails(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-batch-dup-existing")
    client.post(f"/knowledge-bases/{kb['id']}/knowledge-points", json={"title": "existing"})

    resp = client.post(_batch_url(kb["id"]), json={"items": [{"title": "existing"}, {"title": "new-one"}]})
    data = resp.json()["data"]
    assert data["created_count"] == 1
    assert data["failed_count"] == 1
    assert data["results"][0]["status"] == "failed"
    assert data["results"][1]["status"] == "created"


def test_batch_import_duplicate_against_deleted_knowledge_point_fails(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-batch-dup-deleted")
    existing = client.post(
        f"/knowledge-bases/{kb['id']}/knowledge-points", json={"title": "was-deleted"}
    ).json()["data"]
    client.post(
        f"/knowledge-bases/{kb['id']}/knowledge-points/{existing['id']}/delete",
        json={"delete_reason": "x"},
    )

    resp = client.post(_batch_url(kb["id"]), json={"items": [{"title": "was-deleted"}]})
    data = resp.json()["data"]
    assert data["created_count"] == 0
    assert data["failed_count"] == 1
    assert data["results"][0]["reason"] == "知识点标题已存在，请使用其他标题"


def test_batch_import_all_fail_still_returns_200_with_full_result_list(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-batch-all-fail")
    client.post(f"/knowledge-bases/{kb['id']}/knowledge-points", json={"title": "dup-1"})
    client.post(f"/knowledge-bases/{kb['id']}/knowledge-points", json={"title": "dup-2"})

    resp = client.post(_batch_url(kb["id"]), json={"items": [{"title": "dup-1"}, {"title": "dup-2"}]})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["created_count"] == 0
    assert data["failed_count"] == 2
    assert len(data["results"]) == 2


def test_batch_import_empty_items_is_rejected(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-batch-empty")
    resp = client.post(_batch_url(kb["id"]), json={"items": []})
    assert resp.status_code == 422


def test_batch_import_over_500_items_is_rejected(client: TestClient, migrated_schema) -> None:
    kb = _create_kb(client, "kb-batch-toolong")
    items = [{"title": f"kp-{i}"} for i in range(501)]
    resp = client.post(_batch_url(kb["id"]), json={"items": items})
    assert resp.status_code == 422


def test_batch_import_nonexistent_kb_returns_404_and_writes_nothing(client: TestClient, migrated_schema) -> None:
    resp = client.post(_batch_url(999999), json={"items": [{"title": "kp-orphan"}]})
    assert resp.status_code == 404


def test_batch_import_retry_of_same_batch_is_safe_and_reports_all_as_duplicate(
    client: TestClient, migrated_schema
) -> None:
    kb = _create_kb(client, "kb-batch-retry")
    batch = {"items": [{"title": "retry-a"}, {"title": "retry-b"}]}

    first = client.post(_batch_url(kb["id"]), json=batch).json()["data"]
    assert first["created_count"] == 2

    second = client.post(_batch_url(kb["id"]), json=batch).json()["data"]
    assert second["created_count"] == 0
    assert second["failed_count"] == 2

    titles = [kp["title"] for kp in _list_kps(client, kb["id"])]
    assert titles.count("retry-a") == 1
    assert titles.count("retry-b") == 1
