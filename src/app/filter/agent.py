"""
Agent 过滤实现（MiniMax chatcompletion_v2）。

目标输出（JSON）：
- {"keep_ids": ["id1", "id2"]}
或
- {"scored": [{"id":"id1","score":0.91}, ...]}
"""

from __future__ import annotations

from typing import Any

from app.agent import call_minimax_chat, extract_json_object
from app.config import FilterConfig
from app.models import RawItem


def filter_with_agent(items: list[RawItem], filter_config: FilterConfig) -> list[RawItem]:
    if not items:
        return []
    if not filter_config.agent:
        raise ValueError("filter.agent is required for agent filtering")

    cfg = filter_config.agent
    max_n = max(1, min(cfg.max_items_per_call, len(items)))
    subset = items[:max_n]

    items_payload: list[dict[str, Any]] = [
        {
            "id": it.id,
            "source_id": it.source_id,
            "title": it.title,
            "link": it.link,
            "summary": (it.summary or "")[:500],
            "published_at": it.published_at.isoformat() if it.published_at else None,
        }
        for it in subset
    ]

    prompt = cfg.prompt_template or (
        "你是新闻过滤助手。根据用户偏好筛选有价值内容。\n"
        "只允许返回 JSON，不要解释。\n"
        "可返回两种结构之一：\n"
        '1) {"keep_ids": ["..."]}\n'
        '2) {"scored": [{"id":"...","score":0.0}]}\n'
        "items_json:\n{items_json}\n"
        "user_preference:\n{user_preference}\n"
    )
    prompt = (
        prompt.replace("{items_json}", str(items_payload))
        .replace("{user_preference}", cfg.user_preference)
    )

    text = call_minimax_chat(
        endpoint=cfg.endpoint,
        api_key=cfg.api_key,
        model=cfg.model,
        system_name="MiniMax AI",
        user_name="过滤器",
        user_content=prompt,
        timeout_seconds=cfg.timeout_seconds,
    )

    data = extract_json_object(text)

    by_id = {it.id: it for it in subset}
    if "keep_ids" in data and isinstance(data["keep_ids"], list):
        keep_ids = [str(x) for x in data["keep_ids"]]
        return [by_id[i] for i in keep_ids if i in by_id]

    if "scored" in data and isinstance(data["scored"], list):
        pairs: list[tuple[float, RawItem]] = []
        for row in data["scored"]:
            if not isinstance(row, dict):
                continue
            iid = str(row.get("id", ""))
            if iid not in by_id:
                continue
            try:
                score = float(row.get("score", 0.0))
            except Exception:
                score = 0.0
            pairs.append((score, by_id[iid]))
        pairs.sort(key=lambda x: x[0], reverse=True)
        return [it for _, it in pairs]

    raise ValueError(f"agent output invalid: {data}")

