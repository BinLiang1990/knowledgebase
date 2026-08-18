# -*- coding: utf-8 -*-
"""反馈单问题 2 第 2 步：导出 kb=2/3/4 全部知识点的租户归属盘点清单。

只读：走基准版 §5 免鉴权只读面（knowledge-points + answer-groups），不碰数据库。
输出 CSV 供业务侧逐条填写"租户归属"列（填租户标识，或 GLOBAL=列入全局经验白名单）。

用法：python scripts/export_tenant_inventory.py [输出路径，默认 tenant盘点清单.csv]
"""
import csv
import io
import json
import sys
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = "https://platform-enterprise.yicall.com/kb-api"
KBS = {2: "全局打标经验", 3: "打标助手规则库", 4: "操作助手规则库"}


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if body.get("code") != 200:
        raise RuntimeError(f"GET {path} -> {body}")
    return body["data"]


def main() -> None:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "tenant盘点清单.csv"
    rows = []
    for kb_id, kb_name in KBS.items():
        points = get(f"/knowledge-bases/{kb_id}/knowledge-points?status=active")
        print(f"kb={kb_id}({kb_name}): {len(points)} 个知识点")
        for kp in points:
            groups = get(f"/knowledge-bases/{kb_id}/knowledge-points/{kp['id']}/answer-groups")
            live_coords = [
                json.dumps(g["coord"], ensure_ascii=False)
                for g in groups
                if not g.get("revoked") and g.get("live_answer")
            ]
            answer = (kp.get("resolved") or {}).get("answer") or {}
            preview = (answer.get("content") or "").replace("\n", " ")[:60]
            rows.append({
                "kb_id": kb_id,
                "库名": kb_name,
                "kp_id": kp["id"],
                "标题": kp["title"],
                "现有条件组合(live)": " | ".join(live_coords) or "(无生效答案)",
                "内容预览": preview,
                "租户归属(业务填写: 租户标识或GLOBAL)": "",
                "备注": "",
            })
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"共 {len(rows)} 条 -> {out_path}")


if __name__ == "__main__":
    main()
