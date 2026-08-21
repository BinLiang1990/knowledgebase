"""知识库软删除 + 回收站（migration 0009，两级软删）。

口径：仅 deprecated 可删；删除后整库对常规接口隐身（列表/编辑/知识点入口
全 404）；回收站可还原（回到 deprecated）；"彻底删除"也是软删——数据仍在
表里，仅从回收站消失、不可再还原。
"""
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _create(client: TestClient, name: str) -> dict:
    return client.post("/knowledge-bases", json={"name": name}).json()["data"]


def _create_deprecated(client: TestClient, name: str) -> dict:
    kb = _create(client, name)
    return client.post(f"/knowledge-bases/{kb['id']}/deactivate").json()["data"]


def test_delete_active_kb_is_rejected(client: TestClient, migrated_schema) -> None:
    kb = _create(client, "kb-del-active")
    resp = client.post(f"/knowledge-bases/{kb['id']}/delete")
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 444
    assert "停用" in body["msg"]


def test_delete_deprecated_kb_moves_it_to_recycle_bin(client: TestClient, migrated_schema) -> None:
    kb = _create_deprecated(client, "kb-del-ok")

    resp = client.post(f"/knowledge-bases/{kb['id']}/delete")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["deleted_at"] is not None
    # off 模式内置身份 operator="admin"（auth.deps._DEV_USER）
    assert data["deleted_by"] == "admin"

    listed_ids = {row["id"] for row in client.get("/knowledge-bases").json()["data"]}
    assert kb["id"] not in listed_ids

    bin_rows = client.get("/knowledge-bases/recycle-bin").json()["data"]
    assert [row["id"] for row in bin_rows] == [kb["id"]]
    assert bin_rows[0]["status"] == "deprecated"


def test_deleted_kb_is_invisible_to_regular_endpoints(client: TestClient, migrated_schema) -> None:
    kb = _create_deprecated(client, "kb-del-hidden")
    client.post(f"/knowledge-bases/{kb['id']}/delete")

    assert client.patch(f"/knowledge-bases/{kb['id']}", json={"name": "x"}).status_code == 404
    assert client.post(f"/knowledge-bases/{kb['id']}/activate").status_code == 404
    assert client.get(f"/knowledge-bases/{kb['id']}/stats").status_code == 404
    assert client.get(f"/knowledge-bases/{kb['id']}/enabled-dimensions").status_code == 404
    # 知识点入口（_get_kb_or_404）同样 404
    assert client.get(f"/knowledge-bases/{kb['id']}/knowledge-points").status_code == 404
    # 再删一次：已在回收站的库对 delete 也是"不存在"
    assert client.post(f"/knowledge-bases/{kb['id']}/delete").status_code == 404


def test_deleted_kb_name_still_blocks_duplicates(client: TestClient, migrated_schema) -> None:
    """回收站里的库仍占用名称（唯一索引不放松）——放开会造成还原撞名死局。"""
    kb = _create_deprecated(client, "kb-del-name-held")
    client.post(f"/knowledge-bases/{kb['id']}/delete")
    resp = client.post("/knowledge-bases", json={"name": "kb-del-name-held"})
    assert resp.status_code == 400
    assert "名称" in resp.json()["msg"]


def test_restore_puts_kb_back_as_deprecated(client: TestClient, migrated_schema) -> None:
    kb = _create_deprecated(client, "kb-restore")
    client.post(f"/knowledge-bases/{kb['id']}/delete")

    resp = client.post(f"/knowledge-bases/{kb['id']}/restore")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "deprecated"

    listed = {row["id"]: row for row in client.get("/knowledge-bases").json()["data"]}
    assert listed[kb["id"]]["status"] == "deprecated"
    assert client.get("/knowledge-bases/recycle-bin").json()["data"] == []
    # 还原后可正常再启用
    assert client.post(f"/knowledge-bases/{kb['id']}/activate").status_code == 200


def test_restore_requires_kb_in_recycle_bin(client: TestClient, migrated_schema) -> None:
    kb = _create_deprecated(client, "kb-restore-miss")
    assert client.post(f"/knowledge-bases/{kb['id']}/restore").status_code == 404
    assert client.post("/knowledge-bases/999999/restore").status_code == 404


def test_purge_is_soft_and_irreversible(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    kb = _create_deprecated(client, "kb-purge")
    client.post(f"/knowledge-bases/{kb['id']}/delete")

    resp = client.post(f"/knowledge-bases/{kb['id']}/purge")
    assert resp.status_code == 200

    # 回收站消失、常规列表也不出现、不可再还原/再彻底删除
    assert client.get("/knowledge-bases/recycle-bin").json()["data"] == []
    listed_ids = {row["id"] for row in client.get("/knowledge-bases").json()["data"]}
    assert kb["id"] not in listed_ids
    assert client.post(f"/knowledge-bases/{kb['id']}/restore").status_code == 404
    assert client.post(f"/knowledge-bases/{kb['id']}/purge").status_code == 404

    # 软删的意义：行还在表里，purged_at 已置位
    with db_engine.begin() as conn:
        row = conn.execute(
            text("SELECT deleted_at, purged_at FROM knowledge_base WHERE id = :kb"),
            {"kb": kb["id"]},
        ).one()
    assert row.deleted_at is not None
    assert row.purged_at is not None


def test_purge_requires_kb_in_recycle_bin(client: TestClient, migrated_schema) -> None:
    kb = _create_deprecated(client, "kb-purge-miss")
    assert client.post(f"/knowledge-bases/{kb['id']}/purge").status_code == 404


def test_recycle_bin_orders_latest_deleted_first(client: TestClient, migrated_schema) -> None:
    first = _create_deprecated(client, "kb-bin-first")
    second = _create_deprecated(client, "kb-bin-second")
    client.post(f"/knowledge-bases/{first['id']}/delete")
    client.post(f"/knowledge-bases/{second['id']}/delete")

    rows = client.get("/knowledge-bases/recycle-bin").json()["data"]
    assert [row["id"] for row in rows] == [second["id"], first["id"]]
