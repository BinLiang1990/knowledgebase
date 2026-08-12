"""OpenAI 兼容网关客户端（docs/PRD-答案关联.md §4）。

机房 FastGPT/OneAPI 网关转发到 Ollama：embeddings 用于召回，chat 用于
生成关联描述。刻意只依赖 "OpenAI 兼容" 这一契约（/v1/embeddings、
/v1/chat/completions），不绑定任何厂商 SDK —— 换模型/换网关只改配置。

worker 在独立线程里跑，这里用同步 httpx 即可。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("kb_backend")

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (1, 4)  # 第 1、2 次失败后的等待


class GatewayError(Exception):
    """网关调用最终失败（重试耗尽 / 不可重试的错误 / 响应不合契约）。"""


def _post_json(url: str, api_key: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code in _RETRYABLE_STATUS:
                last_error = GatewayError(f"网关返回 {resp.status_code}: {resp.text[:200]}")
            elif resp.status_code != 200:
                # 4xx(除 429) 重试也不会变好，直接失败
                raise GatewayError(f"网关返回 {resp.status_code}: {resp.text[:200]}")
            else:
                return resp.json()
        except GatewayError:
            raise
        except httpx.HTTPError as exc:
            last_error = exc
        if attempt < _MAX_ATTEMPTS - 1:
            time.sleep(_BACKOFF_SECONDS[attempt])
    raise GatewayError(f"网关调用失败（重试 {_MAX_ATTEMPTS} 次）: {last_error}")


def embed_texts(base_url: str, api_key: str, model: str, texts: list[str], timeout: float = 30.0) -> list[list[float]]:
    """一批文本 → 一批向量。返回顺序与输入一致（按响应里的 index 重排，
    不信任网关保序）。"""
    if not texts:
        return []
    data = _post_json(
        base_url.rstrip("/") + "/v1/embeddings",
        api_key,
        {"model": model, "input": texts},
        timeout,
    )
    items = data.get("data")
    if not isinstance(items, list) or len(items) != len(texts):
        raise GatewayError(f"embeddings 响应不合契约：期望 {len(texts)} 条，得到 {items if items is None else len(items)} 条")
    vectors: list[list[float] | None] = [None] * len(texts)
    for item in items:
        idx = item.get("index")
        vec = item.get("embedding")
        if not isinstance(idx, int) or not (0 <= idx < len(texts)) or not isinstance(vec, list):
            raise GatewayError("embeddings 响应不合契约：缺少 index/embedding")
        vectors[idx] = vec
    if any(v is None for v in vectors):
        raise GatewayError("embeddings 响应不合契约：index 不连续")
    return vectors  # type: ignore[return-value]


def chat_completion(
    base_url: str, api_key: str, model: str, system: str, user: str, timeout: float = 120.0
) -> str:
    """单轮 chat，返回助手文本。"""
    data = _post_json(
        base_url.rstrip("/") + "/v1/chat/completions",
        api_key,
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout,
    )
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GatewayError(f"chat 响应不合契约: {str(data)[:200]}") from exc
    if not isinstance(content, str) or not content.strip():
        raise GatewayError("chat 响应为空")
    return content


def parse_json_block(text: str) -> Any:
    """从模型输出里解析 JSON：容忍 ```json 代码围栏与前后闲话。
    本地/网关模型对 response_format 支持不一（PRD §4.2），所以用
    prompt 约束 + 宽松解析，解析失败由调用方决定重试。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        # 去掉第一行围栏(``` 或 ```json)与结尾围栏
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        # 退而求其次：截取首个 { 到最后一个 } 的片段
        start, end = stripped.find("{"), stripped.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(stripped[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise GatewayError(f"模型输出不是合法 JSON: {text[:200]}")
