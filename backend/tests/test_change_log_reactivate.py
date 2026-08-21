"""issue #32：撤回→恢复的变更留痕推导（纯逻辑，构造 Answer 对象直接喂
build_change_log，零 DB、零网络——不使用任何数据库 fixture）。"""
from datetime import datetime

from kb_backend.change_log import build_change_log
from kb_backend.coord import compute_coord_hash
from kb_backend.models.answer import Answer


def _answer(
    id: int,
    kp_id: int,
    created_at: datetime,
    coord: dict | None = None,
    content: str = "content",
    revoked: bool = False,
    revoked_at: datetime | None = None,
    revoked_by: str | None = None,
    revoke_reason: str | None = None,
    reactivated_at: datetime | None = None,
    reactivated_by: str | None = None,
    reactivate_reason: str | None = None,
    operator: str = "admin",
    source: str = "人工填报",
    source_system: str = "tyzsk",
) -> Answer:
    coord = coord or {}
    return Answer(
        id=id,
        knowledge_base_id=1,
        knowledge_point_id=kp_id,
        coord=coord,
        coord_hash=compute_coord_hash(coord),
        content=content,
        effective_time=created_at.date(),
        operator=operator,
        source=source,
        source_system=source_system,
        note=None,
        revoked=revoked,
        revoked_at=revoked_at,
        revoked_by=revoked_by,
        revoke_reason=revoke_reason,
        reactivated_at=reactivated_at,
        reactivated_by=reactivated_by,
        reactivate_reason=reactivate_reason,
        created_at=created_at,
    )


def test_plain_revoked_chain_unchanged() -> None:
    """未恢复的撤回链：行为与 issue #32 之前完全一致（回归保护）。"""
    a = _answer(
        1, kp_id=10, created_at=datetime(2026, 8, 1, 10, 0),
        content="旧说法", revoked=True,
        revoked_at=datetime(2026, 8, 2, 9, 0), revoked_by="admin", revoke_reason="口径作废",
    )
    entries = build_change_log([a])

    assert [e.action for e in entries] == ["revoke", "create"]  # 时间倒序
    revoke = entries[0]
    assert revoke.status == "revoked"
    assert revoke.before_content == "旧说法"
    assert revoke.revoke_reason == "口径作废"
    assert entries[1].status == "revoked"
    assert entries[1].revocable is False


def test_revoke_then_reactivate_with_new_version() -> None:
    """撤回→恢复+追加新版（issue #32 的标准路径）：
    - 撤回条目保留（时间=revoked_at，变更前=撤回当时的内容），状态转"已恢复"；
    - 新增恢复条目（时间=reactivated_at，带恢复原因），状态 live；
    - 新版本行正常 live、可再撤回。"""
    revoked_at = datetime(2026, 8, 2, 9, 0)
    reactivated_at = datetime(2026, 8, 3, 9, 0)
    common = {
        "revoked": False,
        "revoked_at": revoked_at, "revoked_by": "admin", "revoke_reason": "口径作废",
        "reactivated_at": reactivated_at, "reactivated_by": "admin", "reactivate_reason": "口径重新生效",
    }
    v1 = _answer(1, kp_id=10, created_at=datetime(2026, 8, 1, 10, 0), content="旧说法", **common)
    v2 = _answer(2, kp_id=10, created_at=datetime(2026, 8, 3, 9, 0, 1), content="新说法", **common)
    entries = build_change_log([v1, v2])

    assert [e.action for e in entries] == ["edit", "reactivate", "revoke", "create"]

    reactivate = next(e for e in entries if e.action == "reactivate")
    assert reactivate.time == reactivated_at
    assert reactivate.status == "live"
    assert reactivate.reactivate_reason == "口径重新生效"
    # 恢复使"撤回当时的内容"重新生效——新版本 v2 是恢复之后才写入的
    assert reactivate.after_content == "旧说法"
    assert reactivate.revoke_reason is None

    revoke = next(e for e in entries if e.action == "revoke")
    assert revoke.time == revoked_at
    assert revoke.status == "reactivated"  # 这次撤回已被恢复，不再生效
    assert revoke.before_content == "旧说法"  # 不是链上最新的"新说法"
    assert revoke.revoke_reason == "口径作废"

    new_version = next(e for e in entries if e.action == "edit")
    assert new_version.status == "live"
    assert new_version.revocable is True


def test_reactivate_then_revoke_again() -> None:
    """恢复后又被再次撤回：撤回条目回到 revoked（时间取新一轮 revoked_at），
    恢复条目转 superseded；两个条目按各自时间排序。"""
    first_reactivated = datetime(2026, 8, 3, 9, 0)
    second_revoked = datetime(2026, 8, 4, 9, 0)
    a = _answer(
        1, kp_id=10, created_at=datetime(2026, 8, 1, 10, 0), content="旧说法",
        revoked=True,
        revoked_at=second_revoked, revoked_by="admin", revoke_reason="再次作废",
        reactivated_at=first_reactivated, reactivated_by="admin", reactivate_reason="误撤恢复",
    )
    entries = build_change_log([a])

    assert [e.action for e in entries] == ["revoke", "reactivate", "create"]
    assert entries[0].status == "revoked"
    assert entries[0].revoke_reason == "再次作废"
    assert entries[1].status == "superseded"  # 这次恢复已被后来的撤回覆盖


def test_legacy_revoked_row_without_revoked_at_still_logged() -> None:
    """老数据防御：revoked=True 但 revoked_at 缺失（旧过渡实现清空过字段），
    撤回条目不能消失，时间退化为 created_at。"""
    created = datetime(2026, 8, 1, 10, 0)
    a = _answer(1, kp_id=10, created_at=created, revoked=True)
    entries = build_change_log([a])

    revoke = next(e for e in entries if e.action == "revoke")
    assert revoke.time == created
    assert revoke.status == "revoked"


def test_unrevoked_chain_has_no_synthetic_entries() -> None:
    a = _answer(1, kp_id=10, created_at=datetime(2026, 8, 1, 10, 0))
    entries = build_change_log([a])
    assert [e.action for e in entries] == ["create"]
