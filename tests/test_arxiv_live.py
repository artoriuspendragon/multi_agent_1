"""arXiv 线上集成测试（真实网络请求）。

使用方式（默认跳过）：
  RUN_LIVE_ARXIV_TEST=1 PYTHONPATH=src python3 -m pytest tests/test_arxiv_live.py -v

可选环境变量：
  ARXIV_LIVE_DAYS=30
  ARXIV_LIVE_MAX_RESULTS=300
  ARXIV_LIVE_QUERY="(cat:cs.AI OR cat:cs.LG)"
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.config import SourceConfig
from app.sources.api import ApiFetcher


def _utc_window(days: int) -> tuple[str, str]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return start.strftime("%Y%m%d%H%M"), end.strftime("%Y%m%d%H%M")


def _live_enabled() -> bool:
    return os.getenv("RUN_LIVE_ARXIV_TEST", "0") == "1"


def _build_source(
    *,
    comment_mode: str,
    tier_enabled: bool,
    tier_keywords: list[str] | None = None,
) -> SourceConfig:
    days = int(os.getenv("ARXIV_LIVE_DAYS", "30"))
    max_results = int(os.getenv("ARXIV_LIVE_MAX_RESULTS", "300"))
    query = os.getenv("ARXIV_LIVE_QUERY", "(cat:cs.AI OR cat:cs.LG OR cat:cs.CL)")
    start_utc, end_utc = _utc_window(days)

    return SourceConfig(
        id="arxiv-live",
        type="api",
        endpoint="https://export.arxiv.org/api/query",
        response_format="feed",
        comment_mode=comment_mode,  # any | with_comment | without_comment
        comment_tier_filter_enabled=tier_enabled,
        comment_tier_match_mode="any",
        comment_tier_keywords=tier_keywords or [],
        params={
            "search_query": f"{query} AND submittedDate:[{start_utc} TO {end_utc}]",
            "start": "0",
            "max_results": str(max_results),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        },
    )


@pytest.mark.skipif(not _live_enabled(), reason="set RUN_LIVE_ARXIV_TEST=1 to run live arXiv test")
def test_arxiv_live_comment_and_tier_filters() -> None:
    fetcher = ApiFetcher()
    timeout = int(os.getenv("ARXIV_LIVE_TIMEOUT_SECONDS", "30"))

    with httpx.Client(timeout=httpx.Timeout(timeout), follow_redirects=True) as client:
        source_any = _build_source(comment_mode="any", tier_enabled=False)
        source_with_comment = _build_source(comment_mode="with_comment", tier_enabled=False)
        source_high_tier = _build_source(
            comment_mode="with_comment",
            tier_enabled=True,
            # 年份不写死，防止跨年后立即失效
            tier_keywords=[
                "oral",
                "neurips",
                "icml",
                "iclr",
                "cvpr",
                "iccv",
                "eccv",
                "acl",
                "emnlp",
                "naacl",
                "aaai",
                "ijcai",
                "kdd",
                "www",
                "sigir",
                "aistats",
                "icassp",
            ],
        )

        items_any = fetcher.fetch(source_any, client)
        items_with_comment = fetcher.fetch(source_with_comment, client)
        items_high_tier = fetcher.fetch(source_high_tier, client)

    # 基础可用性：至少要有数据
    assert len(items_any) > 0
    # comment 过滤语义
    assert len(items_with_comment) <= len(items_any)
    assert all(bool(it.extra.get("has_comment")) for it in items_with_comment)
    # tier 过滤语义
    assert len(items_high_tier) <= len(items_with_comment)
    for it in items_high_tier:
        comment = str(it.extra.get("comment") or "").lower()
        assert comment
        assert any(k in comment for k in source_high_tier.comment_tier_keywords)

