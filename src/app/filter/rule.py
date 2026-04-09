"""
规则过滤（filter.strategy = 'rule'）。

支持：
- include_keywords（白名单关键词包含：title/summary 任一包含任意关键词则保留）
- exclude_keywords（黑名单关键词排除：title/summary 任一包含任意关键词则丢弃）
- allowed_sources / blocked_sources（来源白/黑名单）
- max_age_hours（发布时间范围：published_at 必须可解析且在最近 N 小时内）
- sort_by（published_at/title/source_id）+ order（asc/desc）
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Iterable

from app.config import FilterConfig
from app.models import RawItem

logger = logging.getLogger(__name__)


def _to_utc(dt: datetime) -> datetime:
    """把 datetime 统一转换到 UTC，若 dt 为 naive 则按 UTC 解释。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _keyword_match(text: str, keywords: Iterable[str]) -> bool:
    t = text.lower()
    for kw in keywords:
        k = kw.strip().lower()
        if not k:
            continue
        if k in t:
            return True
    return False


def _item_text(item: RawItem) -> str:
    title = item.title or ""
    summary = item.summary or ""
    return f"{title}\n{summary}".strip()


def _published_recent_enough(item: RawItem, max_age_hours: int) -> bool:
    # PRD 定义为“只保留过去 N 小时/天内”；但若 published_at 缺失无法判断，
    # 这里采用“宽松策略”：保留该条（避免时间缺失导致误丢）。
    if item.published_at is None:
        return True
    now = datetime.now(timezone.utc)
    published_utc = _to_utc(item.published_at)
    return published_utc >= now - timedelta(hours=max_age_hours)


def _sort_key(item: RawItem, sort_by: str):
    if sort_by == "published_at":
        if item.published_at is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        return _to_utc(item.published_at)
    if sort_by == "title":
        return (item.title or "").lower()
    if sort_by == "source_id":
        return item.source_id
    # 兜底（不应发生）
    return (item.title or "").lower()


def filter_rule_and_sort(items: list[RawItem], filter_config: FilterConfig) -> list[RawItem]:
    include_keywords = filter_config.include_keywords or []
    exclude_keywords = filter_config.exclude_keywords or []
    allowed_sources = filter_config.allowed_sources or []
    blocked_sources = filter_config.blocked_sources or []

    max_age_hours = filter_config.max_age_hours

    # 先过滤
    filtered: list[RawItem] = []
    for item in items:
        if blocked_sources and item.source_id in blocked_sources:
            continue
        if allowed_sources and item.source_id not in allowed_sources:
            continue

        if exclude_keywords:
            if _keyword_match(_item_text(item), exclude_keywords):
                continue

        if include_keywords:
            if not _keyword_match(_item_text(item), include_keywords):
                continue

        if max_age_hours is not None:
            if not _published_recent_enough(item, max_age_hours):
                logger.debug(
                    "[filter] dropped by max_age: title=%s published_at=%s",
                    item.title, item.published_at,
                )
                continue

        filtered.append(item)

    # 再排序
    reverse = filter_config.order == "desc"
    filtered.sort(key=lambda it: _sort_key(it, filter_config.sort_by), reverse=reverse)
    return filtered

