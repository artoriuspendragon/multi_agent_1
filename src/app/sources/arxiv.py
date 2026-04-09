"""
arXiv Fetcher：调用官方 export API（Atom），支持按日期窗口查询和 comment 过滤。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import SourceConfig
from app.models import RawItem

from .base import FetcherError, make_item_ids, normalize_url, parse_datetime

logger = logging.getLogger(__name__)

_DEFAULT_ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_date_window(source: SourceConfig) -> tuple[str, str]:
    # arXiv submittedDate 格式：YYYYMMDDHHMM（UTC）
    if source.arxiv_start and source.arxiv_end:
        return source.arxiv_start, source.arxiv_end
    end = _utc_now()
    start = end - timedelta(days=source.arxiv_days)
    return start.strftime("%Y%m%d%H%M"), end.strftime("%Y%m%d%H%M")


def _extract_arxiv_comment(entry: dict) -> str | None:
    # feedparser 对 namespace 字段通常映射为 arxiv_comment
    comment = (
        entry.get("arxiv_comment")
        or entry.get("comment")
        or entry.get("arxiv:comment")
        or None
    )
    if isinstance(comment, str):
        return comment.strip() or None
    return str(comment).strip() if comment is not None else None


class ArxivFetcher:
    def fetch(self, source: SourceConfig, client: httpx.Client) -> list[RawItem]:
        endpoint = source.endpoint or _DEFAULT_ARXIV_ENDPOINT
        start_utc, end_utc = _resolve_date_window(source)
        base_query = (source.arxiv_search_query or "all:*").strip() or "all:*"
        full_query = f"({base_query}) AND submittedDate:[{start_utc} TO {end_utc}]"

        req_params = {
            "search_query": full_query,
            "start": "0",
            "max_results": str(source.arxiv_max_results),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        # 允许用户用 params 覆盖默认项
        if source.params:
            req_params.update({k: str(v) for k, v in source.params.items()})

        try:
            resp = client.get(endpoint, params=req_params, headers=source.headers)
            logger.info(
                "[arxiv] source=%s endpoint=%s status=%s size=%d query=%s",
                source.id, endpoint, resp.status_code, len(resp.content), req_params.get("search_query"),
            )
            logger.debug("[arxiv] source=%s body=%s", source.id, resp.text[:2000])
            resp.raise_for_status()
        except Exception as e:
            raise FetcherError(f"arxiv request failed: {e}") from e

        try:
            import feedparser
        except Exception as e:
            raise FetcherError(f"feedparser import failed: {e}") from e

        feed = feedparser.parse(resp.content)
        items: list[RawItem] = []
        for entry in getattr(feed, "entries", []) or []:
            if not isinstance(entry, dict):
                continue
            arxiv_comment = _extract_arxiv_comment(entry)
            if source.arxiv_comment_mode == "with_comment" and not arxiv_comment:
                continue
            if source.arxiv_comment_mode == "without_comment" and arxiv_comment:
                continue

            title = (entry.get("title") or "").strip()
            link = entry.get("link") or entry.get("id")
            link = normalize_url(endpoint, str(link) if link is not None else None)
            if not link:
                continue

            summary = entry.get("summary") or entry.get("description") or None
            if isinstance(summary, str):
                summary = summary.strip() or None
            else:
                summary = str(summary).strip() if summary is not None else None

            raw_id = entry.get("id") or link
            published_at = parse_datetime(entry.get("published") or entry.get("updated"))
            item_id, raw_id = make_item_ids(source.id, str(raw_id), link)

            extra = dict(entry)
            extra["arxiv_comment"] = arxiv_comment
            extra["has_comment"] = bool(arxiv_comment)
            logger.info(
                "[arxiv] comment=%s",
                arxiv_comment
            )
            items.append(
                RawItem(
                    id=item_id,
                    source_id=source.id,
                    raw_id=str(raw_id),
                    title=title or link,
                    link=link,
                    summary=summary,
                    published_at=published_at,
                    extra=extra,
                )
            )
        return items

