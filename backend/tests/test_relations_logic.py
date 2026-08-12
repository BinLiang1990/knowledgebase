"""答案关联的纯逻辑测试：余弦、端点规范化、JSON 解析、批量描述生成。

⚠️ 刻意不使用任何数据库 fixture（migrated_schema 会对真实库做
downgrade/upgrade，见 conftest.py）——网关调用全部 monkeypatch，
不发任何网络请求。
"""
from __future__ import annotations

import json

import pytest

import kb_backend.gateway as gateway
import kb_backend.relations as relations
from kb_backend.config import Settings
from kb_backend.gateway import GatewayError, parse_json_block
from kb_backend.relations import ChainEndpoint, content_sha256, cosine, generate_descriptions, normalize_pair

_DB_KW = {"db_host": "x", "db_user": "x", "db_password": "x"}


def _settings(**overrides) -> Settings:
    return Settings(
        **_DB_KW,
        embedding_base_url="http://gw", embedding_model="bge-m3",
        relation_llm_base_url="http://gw", relation_llm_model="qwen",
        **overrides,
    )


def _endpoint(kp_id: int, coord_hash: str, content: str = "内容", kb_id: int = 1) -> ChainEndpoint:
    return ChainEndpoint(
        kb_id=kb_id, kp_id=kp_id, coord_hash=coord_hash, coord={},
        answer_id=1, content=content, content_hash=content_sha256(content),
        kb_name="库", kp_title="点",
    )


# ---------------- 配置降级开关 ----------------

def test_analysis_disabled_by_default():
    assert Settings(**_DB_KW).relation_analysis_enabled is False


def test_analysis_enabled_needs_both_gateways():
    assert _settings().relation_analysis_enabled is True
    # 只配 embedding、缺 chat：仍然 disabled（分析既要召回又要生成）
    partial = Settings(**_DB_KW, embedding_base_url="http://gw", embedding_model="bge-m3")
    assert partial.relation_analysis_enabled is False


# ---------------- 余弦 ----------------

def test_cosine_identical_and_orthogonal():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_guards():
    assert cosine([], []) == 0.0
    assert cosine([1.0], [1.0, 2.0]) == 0.0  # 维度不一致(换向量模型的过渡期)
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0  # 零向量


# ---------------- 端点对规范化 ----------------

def test_normalize_pair_orders_by_kp_then_hash():
    x, y = _endpoint(2, "a" * 64), _endpoint(1, "b" * 64)
    assert normalize_pair(x, y) == (y, x)
    assert normalize_pair(y, x) == (y, x)
    # 同知识点：按 coord_hash 排
    m, n = _endpoint(1, "f" * 64), _endpoint(1, "0" * 64)
    assert normalize_pair(m, n) == (n, m)


# ---------------- 模型输出 JSON 解析 ----------------

def test_parse_json_block_plain_and_fenced():
    assert parse_json_block('{"a": 1}') == {"a": 1}
    assert parse_json_block('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_block('好的，结果如下：\n{"a": 1}\n以上。') == {"a": 1}


def test_parse_json_block_rejects_garbage():
    with pytest.raises(GatewayError):
        parse_json_block("这不是 JSON")


# ---------------- 批量描述生成 ----------------

def test_generate_descriptions_maps_by_index(monkeypatch):
    pairs = [
        (_endpoint(1, "a" * 64, "答案一"), _endpoint(2, "b" * 64, "答案二")),
        (_endpoint(1, "a" * 64, "答案一"), _endpoint(3, "c" * 64, "答案三")),
    ]
    # 模型乱序返回 index，也必须按输入顺序对齐
    reply = json.dumps({"relations": [
        {"index": 1, "description": "描述二"},
        {"index": 0, "description": "描述一"},
    ]}, ensure_ascii=False)
    monkeypatch.setattr(relations, "chat_completion", lambda *a, **k: reply)
    assert generate_descriptions(_settings(), pairs) == ["描述一", "描述二"]


def test_generate_descriptions_retries_once_then_raises(monkeypatch):
    calls = []

    def fake_chat(*a, **k):
        calls.append(1)
        return "不是 JSON"

    monkeypatch.setattr(relations, "chat_completion", fake_chat)
    with pytest.raises(GatewayError):
        generate_descriptions(_settings(), [(_endpoint(1, "a" * 64), _endpoint(2, "b" * 64))])
    assert len(calls) == 2  # 解析失败重试一次(PRD §4.2)


def test_generate_descriptions_missing_index_fails(monkeypatch):
    reply = json.dumps({"relations": [{"index": 0, "description": "只有一条"}]}, ensure_ascii=False)
    monkeypatch.setattr(relations, "chat_completion", lambda *a, **k: reply)
    with pytest.raises(GatewayError):
        generate_descriptions(
            _settings(),
            [(_endpoint(1, "a" * 64), _endpoint(2, "b" * 64)), (_endpoint(1, "a" * 64), _endpoint(3, "c" * 64))],
        )


# ---------------- embeddings 响应契约 ----------------

def test_embed_texts_reorders_by_index(monkeypatch):
    monkeypatch.setattr(
        gateway, "_post_json",
        lambda *a, **k: {"data": [
            {"index": 1, "embedding": [2.0]},
            {"index": 0, "embedding": [1.0]},
        ]},
    )
    assert gateway.embed_texts("http://gw", "", "m", ["一", "二"]) == [[1.0], [2.0]]


def test_embed_texts_rejects_wrong_count(monkeypatch):
    monkeypatch.setattr(gateway, "_post_json", lambda *a, **k: {"data": [{"index": 0, "embedding": [1.0]}]})
    with pytest.raises(GatewayError):
        gateway.embed_texts("http://gw", "", "m", ["一", "二"])


def test_embed_texts_empty_input_no_call(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("不应发起请求")

    monkeypatch.setattr(gateway, "_post_json", boom)
    assert gateway.embed_texts("http://gw", "", "m", []) == []
