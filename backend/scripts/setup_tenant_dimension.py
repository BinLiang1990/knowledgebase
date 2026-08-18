# -*- coding: utf-8 -*-
"""一次性运维脚本：反馈单问题 1 —— 建 tenant 维度并在 kb=2/3/4 启用。

幂等：维度已存在则跳过；启用关系已存在则跳过。只做新增，不删任何数据。
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from sqlalchemy import select

from kb_backend.db import get_session_factory
from kb_backend.models.dimension import DimensionDefinition, KnowledgeBaseEnabledDimension
from kb_backend.models.knowledge_base import KnowledgeBase

TARGET_KBS = [2, 3, 4]

session = get_session_factory()()
try:
    print("== 当前全局维度 ==")
    for d in session.scalars(select(DimensionDefinition)):
        print(f"  key={d.key!r} label={d.label!r} type={d.field_type} weight={d.weight} status={d.status}")

    tenant = session.get(DimensionDefinition, "tenant")
    if tenant is None:
        # weight=60 对齐基准版 §5.1 示例
        tenant = DimensionDefinition(key="tenant", label="tenant", field_type="text", weight=60)
        session.add(tenant)
        session.flush()
        print("-> 已创建维度 tenant (text, weight=60)")
    else:
        print(f"-> 维度已存在: key={tenant.key!r} type={tenant.field_type} status={tenant.status}（跳过创建）")
        if tenant.field_type != "text":
            print("!! field_type 不是 text，与基准版 §3 不符，请人工处理"); session.rollback(); sys.exit(1)

    for kb_id in TARGET_KBS:
        kb = session.get(KnowledgeBase, kb_id)
        if kb is None:
            print(f"!! kb={kb_id} 不存在，跳过")
            continue
        existing = session.get(KnowledgeBaseEnabledDimension, (kb_id, "tenant"))
        if existing is not None:
            print(f"-> kb={kb_id}({kb.name}) 已启用 tenant（跳过）")
        else:
            session.add(KnowledgeBaseEnabledDimension(knowledge_base_id=kb_id, dimension_key="tenant"))
            print(f"-> kb={kb_id}({kb.name}) 新增启用 tenant")

    session.commit()

    print("== 提交后各库启用维度 ==")
    for kb_id in TARGET_KBS:
        keys = session.scalars(
            select(KnowledgeBaseEnabledDimension.dimension_key).where(
                KnowledgeBaseEnabledDimension.knowledge_base_id == kb_id
            )
        ).all()
        print(f"  kb={kb_id}: {keys}")
finally:
    session.close()
