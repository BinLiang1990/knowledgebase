"""GET /knowledge-bases 的服务端过滤与分页（2026-08-21，列表页从前端内存
过滤改为服务端参数）。

- keyword：名称或描述包含，大小写不敏感（列 collation ai_ci）；
- uncategorized=true：仅未分类，与 category_id 互斥；
- page 省略 = 不分页且 data 为数组（对外 §5.7 契约不变）；page 给定时
  data 为 {list, total, page, page_size, summary}。
"""
from fastapi.testclient import TestClient


def _create(client: TestClient, name: str, description: str | None = None, category_id: int | None = None) -> dict:
    payload: dict = {"name": name}
    if description is not None:
        payload["description"] = description
    if category_id is not None:
        payload["category_id"] = category_id
    return client.post("/knowledge-bases", json=payload).json()["data"]


def test_keyword_matches_name_and_description_case_insensitive(
    client: TestClient, migrated_schema
) -> None:
    hit_by_name = _create(client, "kw-FAQ-library")
    hit_by_desc = _create(client, "kw-other", description="常见问题 FAQ 汇总")
    _create(client, "kw-miss", description="无关")

    rows = client.get("/knowledge-bases", params={"keyword": "faq"}).json()["data"]
    assert {row["id"] for row in rows} == {hit_by_name["id"], hit_by_desc["id"]}


def test_keyword_like_wildcards_are_literal(client: TestClient, migrated_schema) -> None:
    """autoescape：% / _ 按字面匹配，不当通配符。"""
    hit = _create(client, "kw-50%off")
    _create(client, "kw-500off")
    rows = client.get("/knowledge-bases", params={"keyword": "50%"}).json()["data"]
    assert [row["id"] for row in rows] == [hit["id"]]


def test_uncategorized_filter(client: TestClient, migrated_schema) -> None:
    category = client.post("/categories", json={"name": "查询用分类"}).json()["data"]
    categorized = _create(client, "kw-cat", category_id=category["id"])
    uncategorized = _create(client, "kw-nocat")

    rows = client.get("/knowledge-bases", params={"uncategorized": "true"}).json()["data"]
    ids = {row["id"] for row in rows}
    assert uncategorized["id"] in ids
    assert categorized["id"] not in ids


def test_uncategorized_and_category_id_are_mutually_exclusive(
    client: TestClient, migrated_schema
) -> None:
    category = client.post("/categories", json={"name": "互斥分类"}).json()["data"]
    resp = client.get(
        "/knowledge-bases",
        params={"uncategorized": "true", "category_id": category["id"]},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 444


def test_pagination_shape_and_slicing(client: TestClient, migrated_schema) -> None:
    ids = [_create(client, f"kw-page-{i}")["id"] for i in range(3)]

    page1 = client.get("/knowledge-bases", params={"page": 1, "page_size": 2}).json()["data"]
    assert page1["total"] == 3
    assert page1["page"] == 1
    assert page1["page_size"] == 2
    assert [row["id"] for row in page1["list"]] == ids[:2]
    assert page1["summary"]["active_total"] == 3
    assert page1["summary"]["active_uncategorized"] == 3

    page2 = client.get("/knowledge-bases", params={"page": 2, "page_size": 2}).json()["data"]
    assert [row["id"] for row in page2["list"]] == ids[2:]

    # page 省略 = 既有契约：data 直接是数组
    legacy = client.get("/knowledge-bases").json()["data"]
    assert isinstance(legacy, list)
    assert [row["id"] for row in legacy] == ids


def test_pagination_filters_compose_and_exclude_deleted(
    client: TestClient, migrated_schema
) -> None:
    kept = _create(client, "kw-compose-keep", description="目标")
    deleted = _create(client, "kw-compose-del", description="目标")
    client.post(f"/knowledge-bases/{deleted['id']}/deactivate")
    client.post(f"/knowledge-bases/{deleted['id']}/delete")

    data = client.get(
        "/knowledge-bases", params={"keyword": "目标", "page": 1, "page_size": 10}
    ).json()["data"]
    assert data["total"] == 1
    assert [row["id"] for row in data["list"]] == [kept["id"]]
    # summary 同样不含回收站里的库
    assert data["summary"]["active_total"] == 1


def test_categories_expose_total_knowledge_base_count(
    client: TestClient, migrated_schema
) -> None:
    """删除拦截口径：total 含已停用与回收站（占用即阻塞），active 不含。"""
    category = client.post("/categories", json={"name": "计数分类"}).json()["data"]
    _create(client, "kw-count-active", category_id=category["id"])
    deprecated = _create(client, "kw-count-dep", category_id=category["id"])
    client.post(f"/knowledge-bases/{deprecated['id']}/deactivate")
    recycled = _create(client, "kw-count-del", category_id=category["id"])
    client.post(f"/knowledge-bases/{recycled['id']}/deactivate")
    client.post(f"/knowledge-bases/{recycled['id']}/delete")

    rows = client.get("/categories").json()["data"]
    row = next(r for r in rows if r["id"] == category["id"])
    assert row["active_knowledge_base_count"] == 1
    assert row["total_knowledge_base_count"] == 3
