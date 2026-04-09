"""
RSS/Atom Fetcher：GET RSS/Atom URL，解析 feed 并映射为 RawItem 列表。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import SourceConfig
from app.models import RawItem

from .base import FetcherError, make_item_ids, normalize_url, parse_datetime

logger = logging.getLogger(__name__)


class RSSFetcher:
    def fetch(self, source: SourceConfig, client: httpx.Client) -> list[RawItem]:
        if not source.url:
            raise FetcherError("rss source requires url")

        # feedparser 可解析 bytes；我们用 httpx 做超时/重试控制
        try:
            resp = client.get(
                source.url,
                params=source.params,
                headers=source.headers,
            )
            logger.info(
                "[rss] source=%s url=%s status=%s size=%d",
                source.id, source.url, resp.status_code, len(resp.content),
            )
            logger.debug("[rss] source=%s body=%s", source.id, resp.text[:2000])
            resp.raise_for_status()
        except Exception as e:
            raise FetcherError(f"rss request failed: {e}") from e

        try:
            import feedparser  # lazy import，避免未使用 RSS 时依赖不可用
        except Exception as e:
            raise FetcherError(f"feedparser import failed: {e}") from e

        feed = feedparser.parse(resp.content)
        items: list[RawItem] = []

        for entry in getattr(feed, "entries", []) or []:
            title = (entry.get("title") or "").strip()
            link = entry.get("link") or entry.get("id") or entry.get("guid")
            link = normalize_url(source.url, str(link) if link is not None else None)
            if not link:
                # 没有 link 无法形成可追踪信息，跳过
                continue

            summary = entry.get("summary") or entry.get("description") or None
            if isinstance(summary, str):
                summary = summary.strip() or None
            else:
                summary = str(summary) if summary is not None else None

            raw_id = entry.get("id") or entry.get("guid") or entry.get("published") or link
            published_at = parse_datetime(entry.get("published") or entry.get("updated"))

            item_id, raw_id = make_item_ids(source.id, str(raw_id), link)
            items.append(
                RawItem(
                    id=item_id,
                    source_id=source.id,
                    raw_id=str(raw_id),
                    title=title or link,
                    link=link,
                    summary=summary,
                    published_at=published_at,
                    extra=dict(entry) if isinstance(entry, dict) else {},
                )
            )

        return items

