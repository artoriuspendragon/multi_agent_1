"""
sources 包对外入口：
- fetch_all：根据配置的 sources 列表拉取并解析出统一 RawItem 列表

内部支持 RSS/ API/ Crawler 三种主类型（并兼容旧的 arxiv 类型映射到 API）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import SourceConfig
from app.models import RawItem

from .api import ApiFetcher
from .base import FetcherError
from .crawler import CrawlerFetcher
from .rss import RSSFetcher

logger = logging.getLogger(__name__)


def _render_date_templates(s: str | None) -> str | None:
    """
    替换 URL 中的日期占位符：
      {{yesterday}}       -> 前一天日期 MM/DD
      {{today}}           -> 今天日期 MM/DD
      {{yesterday_YYYY}}  -> 前一天年份
      {{today_YYYY}}      -> 今天年份
      {{yesterday_MM}}    -> 前一天月份（补零）
      {{yesterday_DD}}    -> 前一天日期（补零）
      {{today_MM}}        -> 今天月份（补零）
      {{today_DD}}        -> 今天日期（补零）
    也支持 strftime 格式：{{today:%Y-%m-%d}}, {{yesterday:%m/%d}}
    """
    if not s or "{{" not in s:
        return s

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    replacements = {
        "{{today}}": now.strftime("%m/%d"),
        "{{yesterday}}": yesterday.strftime("%m/%d"),
        "{{today_YYYY}}": now.strftime("%Y"),
        "{{today_MM}}": now.strftime("%m"),
        "{{today_DD}}": now.strftime("%d"),
        "{{yesterday_YYYY}}": yesterday.strftime("%Y"),
        "{{yesterday_MM}}": yesterday.strftime("%m"),
        "{{yesterday_DD}}": yesterday.strftime("%d"),
    }

    result = s
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)

    # 支持自定义 strftime 格式: {{today:%Y-%m-%d}}, {{yesterday:%m/%d}}
    import re
    for tag, dt in [("today", now), ("yesterday", yesterday)]:
        pattern = r"\{\{" + tag + r":([^}]+)\}\}"
        result = re.sub(pattern, lambda m: dt.strftime(m.group(1)), result)

    return result


def _resolve_source(source: SourceConfig) -> SourceConfig:
    """对 source 的可模板字段做日期模板替换，返回新对象。"""
    new_url = _render_date_templates(source.url)
    new_endpoint = _render_date_templates(source.endpoint)
    new_arxiv_start = _render_date_templates(source.arxiv_start)
    new_arxiv_end = _render_date_templates(source.arxiv_end)
    new_params = None
    if isinstance(source.params, dict):
        new_params = {k: _render_date_templates(str(v)) or "" for k, v in source.params.items()}
    if (
        new_url == source.url
        and new_endpoint == source.endpoint
        and new_arxiv_start == source.arxiv_start
        and new_arxiv_end == source.arxiv_end
        and (new_params == source.params if new_params is not None else source.params is None)
    ):
        return source
    data = source.model_dump()
    if new_url != source.url:
        data["url"] = new_url
    if new_endpoint != source.endpoint:
        data["endpoint"] = new_endpoint
    if new_arxiv_start != source.arxiv_start:
        data["arxiv_start"] = new_arxiv_start
    if new_arxiv_end != source.arxiv_end:
        data["arxiv_end"] = new_arxiv_end
    if new_params is not None and new_params != source.params:
        data["params"] = new_params
    return SourceConfig.model_validate(data)


def _get_fetcher(source_type: str):
    if source_type == "rss":
        return RSSFetcher()
    if source_type == "api":
        return ApiFetcher()
    if source_type == "crawler":
        return CrawlerFetcher()
    if source_type == "arxiv":
        # 兼容旧配置：arxiv 类型走通用 API Fetcher（feed 模式）
        return ApiFetcher()
    raise ValueError(f"unknown source type: {source_type}")


def fetch_all(sources: list[SourceConfig], timeout_per_source: int = 30) -> list[RawItem]:
    """
    拉取所有 sources，并合并为 RawItem 列表。

    - 单个 source 失败：记录日志并继续，避免影响整体早报。
    """
    if not sources:
        return []

    timeout = httpx.Timeout(timeout_per_source)
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }
    items: list[RawItem] = []

    with httpx.Client(timeout=timeout, follow_redirects=True, headers=default_headers) as client:
        for source in sources:
            source = _resolve_source(source)
            fetcher = _get_fetcher(source.type)
            try:
                source_items = fetcher.fetch(source, client)
                items.extend(source_items)
                logger.info("fetched source=%s items=%d", source.id, len(source_items))
            except FetcherError as e:
                logger.warning("source failed source=%s error=%s", source.id, e)
            except Exception:
                logger.exception("unexpected error when fetching source=%s", source.id)

    return items


__all__ = ["fetch_all"]
