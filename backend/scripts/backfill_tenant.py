# -*- coding: utf-8 -*-
"""反馈单问题 2 第 3 步：按盘点清单为存量答案补写 tenant 条件（数据层迁移）。

前置：
  1. 已运行 scripts/setup_tenant_dimension.py（tenant 维度已建并在 kb=2/3/4 启用）；
  2. 业务侧已填完盘点清单 CSV（scripts/export_tenant_inventory.py 导出）的
     "租户归属" 列：填租户标识，或 GLOBAL（列入全局经验白名单，保持 coord 不变）。

行为：对每个非 GLOBAL 的知识点，把其**未撤回**的每条版本链的 coord 合并入
{"tenant": <归属>}（链上所有版本行一起改，保持链完整），并用与写入路径完全相同的
normalize_coord + compute_coord_hash 重算 coord_hash——不走 edit 接口，不产生
撤回/迁移噪音，change-log 历史保持干净。已撤回的链不动（不参与解析与巡检）。

默认 dry-run 只打印；加 --apply 才提交。

用法：python scripts/backfill_tenant.py <盘点清单.csv> [--apply]
"""
import csv
import io
import sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from sqlalchemy import select

from kb_backend.coord import compute_coord_hash, normalize_coord
from kb_backend.db import get_session_factory
from kb_backend.dimensions import get_enabled_dimension_types
from kb_backend.models.answer import Answer

GLOBAL_MARK = "GLOBAL"
TENANT_COL = "租户归属(业务填写: 租户标识或GLOBAL)"


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    csv_path = sys.argv[1]
    apply = "--apply" in sys.argv

    with open(csv_path, encoding="utf-8-sig") as f:
        plan = list(csv.DictReader(f))

    missing = [r for r in plan if not r[TENANT_COL].strip()]
    if missing:
        print(f"!! 盘点未完成：{len(missing)} 条未填写租户归属（如 kp_id={missing[0]['kp_id']}），中止。")
        sys.exit(1)

    session = get_session_factory()()
    changed = skipped_global = 0
    try:
        dim_types_by_kb: dict[int, dict[str, str]] = {}
        for row in plan:
            kb_id, kp_id = int(row["kb_id"]), int(row["kp_id"])
            tenant = row[TENANT_COL].strip()
            if tenant.upper() == GLOBAL_MARK:
                skipped_global += 1
                continue
            if kb_id not in dim_types_by_kb:
                dim_types_by_kb[kb_id] = get_enabled_dimension_types(session, kb_id)
            dim_types = dim_types_by_kb[kb_id]
            if "tenant" not in dim_types:
                print(f"!! kb={kb_id} 未启用 tenant 维度，先跑 setup_tenant_dimension.py，中止。")
                session.rollback()
                sys.exit(1)

            answers = session.scalars(
                select(Answer).where(Answer.knowledge_point_id == kp_id, Answer.revoked.is_(False))
            ).all()
            # 按链（旧 coord_hash）分组整链改写，避免同链版本行新旧 hash 不一致
            chains: dict[str, list[Answer]] = defaultdict(list)
            for a in answers:
                chains[a.coord_hash].append(a)
            for old_hash, chain in chains.items():
                old_coord = chain[0].coord or {}
                if old_coord.get("tenant") == tenant:
                    continue
                new_coord = normalize_coord({**old_coord, "tenant": tenant}, dim_types)
                new_hash = compute_coord_hash(new_coord)
                collide = session.scalars(
                    select(Answer.id).where(
                        Answer.knowledge_point_id == kp_id, Answer.coord_hash == new_hash
                    ).limit(1)
                ).first()
                if collide is not None:
                    print(f"!! kp={kp_id} 目标条件 {new_coord} 已存在版本链（会合并链），请人工处理，跳过该链")
                    continue
                for a in chain:
                    a.coord, a.coord_hash = new_coord, new_hash
                changed += len(chain)
                print(f"kp={kp_id}: {old_coord} -> {new_coord}（{len(chain)} 个版本）")

        if apply:
            session.commit()
            print(f"已提交：改写 {changed} 行答案；GLOBAL 白名单 {skipped_global} 条未动。")
        else:
            session.rollback()
            print(f"[dry-run] 将改写 {changed} 行答案；GLOBAL 白名单 {skipped_global} 条不动。加 --apply 提交。")
    finally:
        session.close()


if __name__ == "__main__":
    main()
