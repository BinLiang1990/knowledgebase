"""知识库分类树 API (PRD §4.11, issue #39)。

覆盖：分类 CRUD 与校验（同级重名/50 字上限/父级存在性/防成环/非空不可删）、
拖拽 move 的三种落点语义与整组重排、知识库挂分类与按分类(含子孙)过滤、
节点计数只统计启用中知识库的口径。

注意：与其他 API 测试一样依赖 migrated_schema——它会对 .env 配置的数据库
做 downgrade base + upgrade head，只能对着专用测试库跑。
"""

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _create_category(client: TestClient, name: str, parent_id: int | None = None) -> dict:
    payload: dict = {"name": name}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    return client.post("/categories", json=payload)


def _create_kb(client: TestClient, name: str, category_id: int | None = None) -> dict:
    payload: dict = {"name": name}
    if category_id is not None:
        payload["category_id"] = category_id
    return client.post("/knowledge-bases", json=payload)


# ---------------- 创建 ----------------


def test_create_top_level_category(client: TestClient, migrated_schema) -> None:
    resp = _create_category(client, "对外服务")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "对外服务"
    assert data["parent_id"] is None
    assert data["sort_order"] == 0
    assert data["active_knowledge_base_count"] == 0


def test_create_child_appends_to_sibling_tail(client: TestClient, migrated_schema) -> None:
    parent = _create_category(client, "公司运营").json()["data"]
    first = _create_category(client, "部门工作", parent["id"]).json()["data"]
    second = _create_category(client, "制度流程", parent["id"]).json()["data"]
    assert first["parent_id"] == parent["id"]
    assert (first["sort_order"], second["sort_order"]) == (0, 1)


def test_create_with_missing_parent_is_404(client: TestClient, migrated_schema) -> None:
    resp = _create_category(client, "孤儿分类", parent_id=99999)
    assert resp.status_code == 404
    assert resp.json()["code"] == 444


def test_create_name_is_stripped(client: TestClient, migrated_schema) -> None:
    resp = _create_category(client, "  运营  ")
    assert resp.json()["data"]["name"] == "运营"


def test_create_blank_name_is_422(client: TestClient, migrated_schema) -> None:
    resp = _create_category(client, "   ")
    assert resp.status_code == 422
    assert resp.json()["code"] == 444


def test_create_name_over_50_chars_is_422(client: TestClient, migrated_schema) -> None:
    resp = _create_category(client, "长" * 51)
    assert resp.status_code == 422
    assert resp.json()["code"] == 444


def test_duplicate_name_same_top_level_parent_is_rejected(
    client: TestClient, migrated_schema
) -> None:
    """顶级分类 parent_id IS NULL——MySQL 唯一索引拦不住这种重名（NULL 不
    参与唯一性），必须由应用级查重兜住。"""
    _create_category(client, "对外服务")
    resp = _create_category(client, "对外服务")
    assert resp.status_code == 400
    assert "同名" in resp.json()["msg"]


def test_duplicate_name_same_parent_case_insensitive(client: TestClient, migrated_schema) -> None:
    parent = _create_category(client, "父级").json()["data"]
    _create_category(client, "faq", parent["id"])
    resp = _create_category(client, "FAQ", parent["id"])
    assert resp.status_code == 400


def test_same_name_under_different_parents_is_allowed(
    client: TestClient, migrated_schema
) -> None:
    p1 = _create_category(client, "产品部").json()["data"]
    p2 = _create_category(client, "数据部").json()["data"]
    assert _create_category(client, "业务经验", p1["id"]).status_code == 200
    assert _create_category(client, "业务经验", p2["id"]).status_code == 200


# ---------------- 列表与计数 ----------------


def test_list_is_flat_ordered_and_counts_only_active_kbs(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    parent = _create_category(client, "公司运营").json()["data"]
    child = _create_category(client, "部门工作", parent["id"]).json()["data"]
    _create_kb(client, "kb-in-child", child["id"])
    deprecated = _create_kb(client, "kb-deprecated", child["id"]).json()["data"]
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE knowledge_base SET status='deprecated' WHERE id=:kb"),
            {"kb": deprecated["id"]},
        )

    resp = client.get("/categories")
    assert resp.status_code == 200
    rows = resp.json()["data"]
    by_id = {row["id"]: row for row in rows}
    # 直属计数只统计启用中的知识库（PRD §4.11 未决 #1 建议口径）；
    # 子树合计由前端聚合，父节点自身直属为 0
    assert by_id[child["id"]]["active_knowledge_base_count"] == 1
    assert by_id[parent["id"]]["active_knowledge_base_count"] == 0


# ---------------- 修改（改名 / 换父级） ----------------


def test_update_rename_duplicate_in_same_parent_is_rejected(
    client: TestClient, migrated_schema
) -> None:
    _create_category(client, "甲")
    other = _create_category(client, "乙").json()["data"]
    resp = client.patch(f"/categories/{other['id']}", json={"name": "甲"})
    assert resp.status_code == 400


def test_update_move_to_own_descendant_is_rejected(client: TestClient, migrated_schema) -> None:
    root = _create_category(client, "根").json()["data"]
    mid = _create_category(client, "中", root["id"]).json()["data"]
    leaf = _create_category(client, "叶", mid["id"]).json()["data"]
    resp = client.patch(f"/categories/{root['id']}", json={"parent_id": leaf["id"]})
    assert resp.status_code == 400
    assert "子孙" in resp.json()["msg"]
    # 移到自己下面同样拒绝
    resp = client.patch(f"/categories/{root['id']}", json={"parent_id": root["id"]})
    assert resp.status_code == 400


def test_update_change_parent_appends_to_new_sibling_tail(
    client: TestClient, migrated_schema
) -> None:
    a = _create_category(client, "A").json()["data"]
    b = _create_category(client, "B").json()["data"]
    _create_category(client, "B-1", b["id"])
    moved = client.patch(f"/categories/{a['id']}", json={"parent_id": b["id"]}).json()["data"]
    assert moved["parent_id"] == b["id"]
    assert moved["sort_order"] == 1  # 排到 B-1 之后


def test_update_parent_id_null_moves_to_top_level(client: TestClient, migrated_schema) -> None:
    parent = _create_category(client, "父").json()["data"]
    child = _create_category(client, "子", parent["id"]).json()["data"]
    moved = client.patch(f"/categories/{child['id']}", json={"parent_id": None}).json()["data"]
    assert moved["parent_id"] is None


# ---------------- 删除 ----------------


def test_delete_empty_category_succeeds(client: TestClient, migrated_schema) -> None:
    created = _create_category(client, "临时分类").json()["data"]
    resp = client.delete(f"/categories/{created['id']}")
    assert resp.status_code == 200
    ids = [row["id"] for row in client.get("/categories").json()["data"]]
    assert created["id"] not in ids


def test_delete_category_with_children_is_rejected_with_counts(
    client: TestClient, migrated_schema
) -> None:
    parent = _create_category(client, "父").json()["data"]
    _create_category(client, "子", parent["id"])
    resp = client.delete(f"/categories/{parent['id']}")
    assert resp.status_code == 400
    assert "1 个子分类" in resp.json()["msg"]


def test_delete_category_with_deprecated_kb_is_rejected(
    client: TestClient, migrated_schema, db_engine: Engine
) -> None:
    """知识库占用「含已停用的」——停用的库也阻塞删除（PRD §4.11）。"""
    category = _create_category(client, "占用分类").json()["data"]
    kb = _create_kb(client, "kb-occupies", category["id"]).json()["data"]
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE knowledge_base SET status='deprecated' WHERE id=:kb"), {"kb": kb["id"]}
        )
    resp = client.delete(f"/categories/{category['id']}")
    assert resp.status_code == 400
    assert "1 个知识库" in resp.json()["msg"]


# ---------------- 拖拽 move ----------------


def test_move_before_and_after_reorders_siblings(client: TestClient, migrated_schema) -> None:
    a = _create_category(client, "A").json()["data"]
    b = _create_category(client, "B").json()["data"]
    c = _create_category(client, "C").json()["data"]

    # C 拖到 A 前面：期望顺序 C A B
    resp = client.post(f"/categories/{c['id']}/move", json={"target_id": a["id"], "position": "before"})
    assert resp.status_code == 200
    rows = client.get("/categories").json()["data"]
    top = [r["id"] for r in rows if r["parent_id"] is None]
    assert top == [c["id"], a["id"], b["id"]]

    # A 拖到 B 后面：期望顺序 C B A
    client.post(f"/categories/{a['id']}/move", json={"target_id": b["id"], "position": "after"})
    rows = client.get("/categories").json()["data"]
    top = [r["id"] for r in rows if r["parent_id"] is None]
    assert top == [c["id"], b["id"], a["id"]]


def test_move_inside_appends_as_last_child_of_target(client: TestClient, migrated_schema) -> None:
    target = _create_category(client, "目标").json()["data"]
    _create_category(client, "既有子级", target["id"])
    dragged = _create_category(client, "被拖").json()["data"]
    resp = client.post(
        f"/categories/{dragged['id']}/move", json={"target_id": target["id"], "position": "inside"}
    )
    data = resp.json()["data"]
    assert data["parent_id"] == target["id"]
    assert data["sort_order"] == 1


def test_move_into_own_descendant_is_rejected(client: TestClient, migrated_schema) -> None:
    root = _create_category(client, "根").json()["data"]
    leaf = _create_category(client, "叶", root["id"]).json()["data"]
    resp = client.post(
        f"/categories/{root['id']}/move", json={"target_id": leaf["id"], "position": "inside"}
    )
    assert resp.status_code == 400
    resp = client.post(
        f"/categories/{root['id']}/move", json={"target_id": root["id"], "position": "before"}
    )
    assert resp.status_code == 400


def test_move_cross_parent_duplicate_name_is_rejected(client: TestClient, migrated_schema) -> None:
    """落点导致改挂父级时执行同级重名校验，重名整体不生效（PRD §4.11）。"""
    p1 = _create_category(client, "产品部").json()["data"]
    p2 = _create_category(client, "数据部").json()["data"]
    _create_category(client, "业务经验", p1["id"])
    dup = _create_category(client, "业务经验", p2["id"]).json()["data"]
    resp = client.post(
        f"/categories/{dup['id']}/move", json={"target_id": p1["id"], "position": "inside"}
    )
    assert resp.status_code == 400
    # 整体不生效：父级保持原样
    rows = client.get("/categories").json()["data"]
    assert next(r for r in rows if r["id"] == dup["id"])["parent_id"] == p2["id"]


# ---------------- 知识库挂分类与按分类过滤 ----------------


def test_kb_create_with_category_and_out_fields(client: TestClient, migrated_schema) -> None:
    category = _create_category(client, "对外服务").json()["data"]
    data = _create_kb(client, "kb-with-cat", category["id"]).json()["data"]
    assert data["category_id"] == category["id"]
    assert data["category_name"] == "对外服务"


def test_kb_create_without_category_is_uncategorized(client: TestClient, migrated_schema) -> None:
    data = _create_kb(client, "kb-no-cat").json()["data"]
    assert data["category_id"] is None
    assert data["category_name"] is None


def test_kb_create_with_missing_category_is_404(client: TestClient, migrated_schema) -> None:
    resp = _create_kb(client, "kb-bad-cat", 99999)
    assert resp.status_code == 404
    assert resp.json()["code"] == 444


def test_kb_update_set_and_clear_category(client: TestClient, migrated_schema) -> None:
    category = _create_category(client, "运营").json()["data"]
    kb = _create_kb(client, "kb-move-cat").json()["data"]

    updated = client.patch(
        f"/knowledge-bases/{kb['id']}", json={"category_id": category["id"]}
    ).json()["data"]
    assert updated["category_id"] == category["id"]

    # 显式 null = 置为未分类；省略 = 不改（分别验证）
    untouched = client.patch(f"/knowledge-bases/{kb['id']}", json={"name": "kb-move-cat-2"}).json()[
        "data"
    ]
    assert untouched["category_id"] == category["id"]
    cleared = client.patch(f"/knowledge-bases/{kb['id']}", json={"category_id": None}).json()["data"]
    assert cleared["category_id"] is None


def test_kb_list_filter_by_category_includes_descendants(
    client: TestClient, migrated_schema
) -> None:
    root = _create_category(client, "公司运营").json()["data"]
    child = _create_category(client, "部门工作", root["id"]).json()["data"]
    grand = _create_category(client, "研发实验小组", child["id"]).json()["data"]
    _create_kb(client, "kb-root", root["id"])
    _create_kb(client, "kb-grand", grand["id"])
    _create_kb(client, "kb-outside")

    resp = client.get("/knowledge-bases", params={"category_id": root["id"]})
    names = [row["name"] for row in resp.json()["data"]]
    assert sorted(names) == ["kb-grand", "kb-root"]

    resp = client.get("/knowledge-bases", params={"category_id": grand["id"]})
    names = [row["name"] for row in resp.json()["data"]]
    assert names == ["kb-grand"]


def test_kb_list_filter_with_missing_category_is_404(client: TestClient, migrated_schema) -> None:
    """不存在的分类 id 报错而不是静默空列表（PRD §4.11 校验规则）。"""
    resp = client.get("/knowledge-bases", params={"category_id": 99999})
    assert resp.status_code == 404
    assert resp.json()["code"] == 444
