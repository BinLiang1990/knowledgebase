"""答案关联服务层（docs/PRD-答案关联.md §3/§4）。

核心对象是"端点" = 一条版本链 (knowledge_point_id, coord_hash) 的当前生效
版本。分析流程：向量补齐(按内容哈希增量) → 全库余弦召回 Top-K → LLM 批量
生成描述 → upsert 关联。manual 来源的关联永不被 AI 覆盖（PRD §0.10）。

规模预期几千知识点/万级端点：召回用纯 Python 余弦(万级 × ~1024 维，秒级，
worker 线程内可接受)，刻意不引入 numpy/向量库（PRD §4.3）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .gateway import GatewayError, chat_completion, embed_texts, parse_json_block
from .models.answer import Answer
from .models.knowledge_base import KnowledgeBase
from .models.knowledge_point import KnowledgePoint
from .models.relation import AnswerEmbedding, AnswerRelation, RelationTask

logger = logging.getLogger("kb_backend")

RETRY_LIMIT = 3


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChainEndpoint:
    kb_id: int
    kp_id: int
    coord_hash: str
    coord: dict[str, Any]
    answer_id: int
    content: str
    content_hash: str
    kb_name: str
    kp_title: str

    @property
    def key(self) -> tuple[int, str]:
        return (self.kp_id, self.coord_hash)


def normalize_pair(x: ChainEndpoint, y: ChainEndpoint) -> tuple[ChainEndpoint, ChainEndpoint]:
    """端点按 (kp_id, coord_hash) 排序规范化，保证同一对只有一种落库顺序。"""
    return (x, y) if x.key <= y.key else (y, x)


def collect_endpoints(db: Session, kp_id: int | None = None) -> list[ChainEndpoint]:
    """枚举有效端点：启用中的知识库 × 未删除知识点 × 有生效版本的未撤回链。
    kp_id 给定时只枚举该知识点（不校验知识库启用状态——调用方已经做过
    kb/kp 存在性校验）。

    刻意不复用 resolve.compute_live_groups（它按单知识点查询，全库枚举会
    退化成几千次查询）：这里一次性取全部候选行，在 Python 里做和它相同的
    max(effective_time, created_at, id) 选链。"""
    today = date.today()
    stmt = (
        select(
            Answer,
            KnowledgePoint.title,
            KnowledgeBase.name,
        )
        .join(KnowledgePoint, (KnowledgePoint.id == Answer.knowledge_point_id)
              & (KnowledgePoint.knowledge_base_id == Answer.knowledge_base_id))
        .join(KnowledgeBase, KnowledgeBase.id == Answer.knowledge_base_id)
        .where(
            Answer.revoked.is_(False),
            Answer.effective_time <= today,
            KnowledgePoint.status == "active",
        )
    )
    if kp_id is not None:
        stmt = stmt.where(Answer.knowledge_point_id == kp_id)
    else:
        stmt = stmt.where(KnowledgeBase.status == "active")

    best: dict[tuple[int, str], tuple[Answer, str, str]] = {}
    for answer, kp_title, kb_name in db.execute(stmt).all():
        key = (answer.knowledge_point_id, answer.coord_hash)
        current = best.get(key)
        if current is None or (
            (answer.effective_time, answer.created_at, answer.id)
            > (current[0].effective_time, current[0].created_at, current[0].id)
        ):
            best[key] = (answer, kp_title, kb_name)

    return [
        ChainEndpoint(
            kb_id=a.knowledge_base_id,
            kp_id=a.knowledge_point_id,
            coord_hash=a.coord_hash,
            coord=a.coord,
            answer_id=a.id,
            content=a.content,
            content_hash=content_sha256(a.content),
            kb_name=kb_name,
            kp_title=kp_title,
        )
        for a, kp_title, kb_name in best.values()
    ]


# ---------------- 向量 ----------------

def _embedding_text(ep: ChainEndpoint, max_chars: int) -> str:
    return ep.kp_title + "\n" + ep.content[:max_chars]


def sync_embeddings(
    db: Session,
    endpoints: list[ChainEndpoint],
    settings: Settings,
    progress: Callable[[int, int], None] | None = None,
) -> dict[tuple[int, str], list[float]]:
    """确保每个端点都有与"当前内容哈希 + 当前向量模型"一致的向量缓存，
    返回 key → vector。内容没变的端点零成本命中缓存（PRD §8.3）。"""
    keys = {ep.key for ep in endpoints}
    rows = db.execute(select(AnswerEmbedding)).scalars().all()
    cache = {(r.knowledge_point_id, r.coord_hash): r for r in rows if (r.knowledge_point_id, r.coord_hash) in keys}

    stale = [
        ep for ep in endpoints
        if (row := cache.get(ep.key)) is None
        or row.content_hash != ep.content_hash
        or row.model != settings.embedding_model
    ]
    total = len(stale)
    done = 0
    if progress:
        progress(done, total)

    batch_size = max(1, settings.relation_embed_batch)
    for start in range(0, total, batch_size):
        batch = stale[start : start + batch_size]
        vectors = embed_texts(
            settings.embedding_base_url,
            settings.embedding_api_key,
            settings.embedding_model,
            [_embedding_text(ep, settings.relation_max_content_chars) for ep in batch],
        )
        for ep, vec in zip(batch, vectors):
            row = cache.get(ep.key)
            if row is None:
                row = AnswerEmbedding(
                    knowledge_base_id=ep.kb_id,
                    knowledge_point_id=ep.kp_id,
                    coord_hash=ep.coord_hash,
                    content_hash=ep.content_hash,
                    model=settings.embedding_model,
                    vector=vec,
                )
                db.add(row)
                cache[ep.key] = row
            else:
                row.content_hash = ep.content_hash
                row.model = settings.embedding_model
                row.vector = vec
        # 每批一提交：进程中途挂掉时已算的向量不作废
        db.commit()
        done += len(batch)
        if progress:
            progress(done, total)

    return {key: list(row.vector) for key, row in cache.items()}


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = num_a = num_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        num_a += x * x
        num_b += y * y
    if num_a <= 0 or num_b <= 0:
        return 0.0
    return dot / (math.sqrt(num_a) * math.sqrt(num_b))


# ---------------- 描述生成 ----------------

_SYSTEM_PROMPT = (
    "你是企业知识库的关联分析助手。用户会给出若干对答案，每条答案来自某个知识库的某个知识点，"
    "并带有它的适用维度条件。请为每一对写一段 100~300 字的中文关联描述，说明：\n"
    "1. 两条答案各自适用的范围（知识库/知识点/维度条件）差异；\n"
    "2. 内容上的关系：一致 / 互补 / 收窄 / 引用 / 上下游 / 冲突等；\n"
    "3. 若内容存在明显矛盾，必须明确指出矛盾点。\n"
    '只输出 JSON，格式：{"relations": [{"index": 0, "description": "..."}]}，'
    "index 与输入的每一对的 index 一一对应，不要输出任何其他文字。"
)


def _pair_payload(index: int, x: ChainEndpoint, y: ChainEndpoint, max_chars: int) -> dict[str, Any]:
    def side(ep: ChainEndpoint) -> dict[str, Any]:
        return {
            "知识库": ep.kb_name,
            "知识点": ep.kp_title,
            "维度条件": ep.coord if ep.coord else "默认（处处适用）",
            "内容": ep.content[: max_chars] + ("…（已截断）" if len(ep.content) > max_chars else ""),
        }

    return {"index": index, "答案A": side(x), "答案B": side(y)}


def generate_descriptions(
    settings: Settings, pairs: list[tuple[ChainEndpoint, ChainEndpoint]]
) -> list[str]:
    """一次 chat 调用为一批关联对生成描述，按输入顺序返回。解析失败重试
    一次（PRD §4.2），仍失败抛 GatewayError 交给任务重试机制。"""
    payload = json.dumps(
        {"pairs": [_pair_payload(i, x, y, settings.relation_max_content_chars) for i, (x, y) in enumerate(pairs)]},
        ensure_ascii=False,
    )
    last_error: GatewayError | None = None
    for _ in range(2):
        text = chat_completion(
            settings.relation_llm_base_url,
            settings.relation_llm_api_key,
            settings.relation_llm_model,
            _SYSTEM_PROMPT,
            payload,
        )
        try:
            data = parse_json_block(text)
            items = data.get("relations") if isinstance(data, dict) else None
            if not isinstance(items, list):
                raise GatewayError("模型输出缺少 relations 数组")
            by_index = {
                item["index"]: str(item["description"]).strip()
                for item in items
                if isinstance(item, dict) and isinstance(item.get("index"), int) and item.get("description")
            }
            missing = [i for i in range(len(pairs)) if i not in by_index]
            if missing:
                raise GatewayError(f"模型输出缺少 index {missing} 的描述")
            return [by_index[i] for i in range(len(pairs))]
        except GatewayError as exc:
            last_error = exc
    raise last_error  # type: ignore[misc]


# ---------------- 关联 upsert ----------------

def find_relation(db: Session, x: ChainEndpoint, y: ChainEndpoint) -> AnswerRelation | None:
    a, b = normalize_pair(x, y)
    return db.execute(
        select(AnswerRelation).where(
            AnswerRelation.kp_a_id == a.kp_id,
            AnswerRelation.coord_hash_a == a.coord_hash,
            AnswerRelation.kp_b_id == b.kp_id,
            AnswerRelation.coord_hash_b == b.coord_hash,
        )
    ).scalar_one_or_none()


def upsert_ai_relation(
    db: Session,
    x: ChainEndpoint,
    y: ChainEndpoint,
    description: str,
    similarity: float | None,
    settings: Settings,
) -> AnswerRelation:
    a, b = normalize_pair(x, y)
    existing = find_relation(db, a, b)
    if existing is not None and existing.source == "manual":
        # 调用方本应已过滤，双保险：手动维护的不覆盖
        return existing
    if existing is None:
        existing = AnswerRelation(
            kb_a_id=a.kb_id, kp_a_id=a.kp_id, coord_hash_a=a.coord_hash, coord_a=a.coord,
            kb_b_id=b.kb_id, kp_b_id=b.kp_id, coord_hash_b=b.coord_hash, coord_b=b.coord,
            description=description, source="ai", operator="admin",
        )
        db.add(existing)
    existing.description = description
    existing.source = "ai"
    existing.similarity = round(similarity, 4) if similarity is not None else existing.similarity
    existing.model = settings.relation_llm_model
    existing.answer_a_id, existing.content_hash_a = a.answer_id, a.content_hash
    existing.answer_b_id, existing.content_hash_b = b.answer_id, b.content_hash
    existing.coord_a, existing.coord_b = a.coord, b.coord
    return existing


# ---------------- 任务登记 ----------------

def schedule_analyze_task(
    db: Session, kb_id: int, kp_id: int, coord_hash: str | None, operator: str = "admin"
) -> RelationTask:
    """同目标已有进行中任务则复用（PRD §3.1），不重复登记。"""
    stmt = select(RelationTask).where(
        RelationTask.kind == "analyze",
        RelationTask.knowledge_point_id == kp_id,
        RelationTask.status.in_(("pending", "generating")),
        RelationTask.center_coord_hash.is_(None) if coord_hash is None
        else RelationTask.center_coord_hash == coord_hash,
    )
    existing = db.execute(stmt.limit(1)).scalar_one_or_none()
    if existing is not None:
        return existing
    task = RelationTask(
        kind="analyze", knowledge_base_id=kb_id, knowledge_point_id=kp_id,
        center_coord_hash=coord_hash, status="pending", operator=operator,
    )
    db.add(task)
    return task


def schedule_generate_pair_task(
    db: Session, kb_id: int, kp_id: int, relation_id: int, operator: str = "admin"
) -> RelationTask:
    stmt = select(RelationTask).where(
        RelationTask.kind == "generate_pair",
        RelationTask.pair_relation_id == relation_id,
        RelationTask.status.in_(("pending", "generating")),
    )
    existing = db.execute(stmt.limit(1)).scalar_one_or_none()
    if existing is not None:
        return existing
    task = RelationTask(
        kind="generate_pair", knowledge_base_id=kb_id, knowledge_point_id=kp_id,
        pair_relation_id=relation_id, status="pending", operator=operator,
    )
    db.add(task)
    return task


# ---------------- 任务执行（worker 调用） ----------------

def _update_progress(db: Session, task: RelationTask, phase: str, done: int, total: int) -> None:
    task.phase = phase
    task.progress_done = done
    task.progress_total = total
    db.commit()


def execute_analyze_task(db: Session, task: RelationTask, settings: Settings) -> None:
    """analyze：center_coord_hash 为空 = 知识点级自动关联（全部链逐条召回）。"""
    centers = [
        ep for ep in collect_endpoints(db, kp_id=task.knowledge_point_id)
        if task.center_coord_hash is None or ep.coord_hash == task.center_coord_hash
    ]
    if not centers:
        # 链已被撤回/知识点已删除：任务空跑完成，不算失败
        _update_progress(db, task, "generate", 0, 0)
        return

    corpus = collect_endpoints(db)
    vectors = sync_embeddings(
        db, corpus, settings,
        progress=lambda done, total: _update_progress(db, task, "embedding", done, total),
    )

    _update_progress(db, task, "recall", 0, len(centers))
    by_key = {ep.key: ep for ep in corpus}
    # 跨多个 center 去重：同一对只生成一次
    candidates: dict[tuple[tuple[int, str], tuple[int, str]], tuple[ChainEndpoint, ChainEndpoint, float]] = {}
    for i, center in enumerate(centers, start=1):
        center_vec = vectors.get(center.key)
        if center_vec is None:
            continue
        scored = [
            (other_key, cosine(center_vec, vec))
            for other_key, vec in vectors.items()
            if other_key != center.key and other_key in by_key
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        for other_key, sim in scored[: max(1, settings.relation_top_k)]:
            if sim < settings.relation_min_similarity:
                break
            a, b = normalize_pair(center, by_key[other_key])
            candidates.setdefault((a.key, b.key), (a, b, sim))
        _update_progress(db, task, "recall", i, len(centers))

    # 过滤：manual 不覆盖；ai 且两端内容都没变的跳过（零 LLM 成本）
    to_generate: list[tuple[ChainEndpoint, ChainEndpoint, float]] = []
    for a, b, sim in candidates.values():
        existing = find_relation(db, a, b)
        if existing is not None:
            if existing.source == "manual":
                continue
            if (
                existing.description
                and existing.content_hash_a == a.content_hash
                and existing.content_hash_b == b.content_hash
            ):
                continue
        to_generate.append((a, b, sim))

    _update_progress(db, task, "generate", 0, len(to_generate))
    batch_size = max(1, settings.relation_gen_batch)
    generated = 0
    for start in range(0, len(to_generate), batch_size):
        batch = to_generate[start : start + batch_size]
        descriptions = generate_descriptions(settings, [(a, b) for a, b, _ in batch])
        for (a, b, sim), description in zip(batch, descriptions):
            upsert_ai_relation(db, a, b, description, sim, settings)
        generated += len(batch)
        # 每批一提交：部分成功的批次不因后续批次失败而回滚
        _update_progress(db, task, "generate", generated, len(to_generate))


def execute_generate_pair_task(db: Session, task: RelationTask, settings: Settings) -> None:
    relation = db.get(AnswerRelation, task.pair_relation_id)
    if relation is None:
        raise GatewayError("关联已被删除，无法生成描述")
    eps_a = {ep.key: ep for ep in collect_endpoints(db, kp_id=relation.kp_a_id)}
    eps_b = {ep.key: ep for ep in collect_endpoints(db, kp_id=relation.kp_b_id)}
    a = eps_a.get((relation.kp_a_id, relation.coord_hash_a))
    b = eps_b.get((relation.kp_b_id, relation.coord_hash_b))
    if a is None or b is None:
        raise GatewayError("关联的某一端已不可用（撤回或知识点已删除），无法生成描述")
    _update_progress(db, task, "generate", 0, 1)
    description = generate_descriptions(settings, [(a, b)])[0]
    # 重新生成即接受 AI 内容：source 转回 ai（PRD §3.5）
    upsert_ai_relation(db, a, b, description, relation.similarity, settings)
    _update_progress(db, task, "generate", 1, 1)
