"""
网页抓取 Fetcher：对非 RSS/API 的页面执行轻量抓取，并映射为 RawItem。

PRD 未定义 crawler 的 selector 细节，因此这里采用“最低可用策略”：
- 若 source.selector 给出：将其作为 CSS 选择器，遍历匹配元素
  - 从元素内部优先找第一个 <a href> 作为 link
  - title 优先取 <a> 文本，否则使用元素文本
- 若 source.selector 未提供：抓取 <title> 与正文中的第一个 <a href> 组合为一条 RawItem
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import SourceConfig
from app.models import RawItem

from .base import FetcherError, make_item_ids, normalize_url, parse_datetime

logger = logging.getLogger(__name__)


class CrawlerFetcher:
    def fetch(self, source: SourceConfig, client: httpx.Client) -> list[RawItem]:
        if not source.url:
            raise FetcherError("crawler source requires url")

        try:
            resp = client.get(
                source.url,
                params=source.params,
                headers=source.headers,
            )
            logger.info(
                "[crawler] source=%s url=%s status=%s size=%d",
                source.id, source.url, resp.status_code, len(resp.content),
            )
            logger.debug("[crawler] source=%s body=%s", source.id, resp.text[:2000])
            resp.raise_for_status()
        except Exception as e:
            raise FetcherError(f"crawler request failed: {e}") from e

        try:
            from bs4 import BeautifulSoup  # lazy import
        except Exception as e:
            raise FetcherError(f"beautifulsoup4 import failed: {e}") from e

        soup = BeautifulSoup(resp.text, "html.parser")
        items: list[RawItem] = []

        base = source.url
        if source.selector:
            elements = soup.select(source.selector)
            for el in elements:
                a = el.select_one("a[href]") if hasattr(el, "select_one") else None
                link = None
                title = None
                if a is not None:
                    link = a.get("href")
                    title = a.get_text(strip=True)
                if not link:
                    # 若没有 href，则尝试从元素属性取值（可能用于自定义渲染）
                    link = el.get("href") if hasattr(el, "get") else None
                link = normalize_url(base, link)
                if not link:
                    continue

                if not title:
                    title = el.get_text(strip=True) if hasattr(el, "get_text") else link

                raw_id = link
                item_id, raw_id = make_item_ids(source.id, raw_id, link)
                items.append(
                    RawItem(
                        id=item_id,
                        source_id=source.id,
                        raw_id=str(raw_id),
                        title=str(title).strip() or link,
                        link=link,
                        summary=None,
                        published_at=None,
                        extra={},
                    )
                )
        else:
            page_title = (soup.title.get_text(strip=True) if soup.title else "").strip()
            # 取第一个正文链接
            first_a = soup.select_one("a[href]")
            link = normalize_url(base, first_a.get("href") if first_a else None)
            if link:
                item_id, raw_id = make_item_ids(source.id, link, link)
                items.append(
                    RawItem(
                        id=item_id,
                        source_id=source.id,
                        raw_id=str(raw_id),
                        title=page_title or link,
                        link=link,
                        summary=None,
                        published_at=None,
                        extra={},
                    )
                )

        return items

