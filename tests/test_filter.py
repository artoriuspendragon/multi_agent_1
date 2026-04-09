"""单元测试：filter 规则过滤（filter.strategy='rule'）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import FilterConfig
from app.filter.rule import filter_rule_and_sort
from app.models import RawItem


def _raw(
    *,
    id_: str,
    source_id: str,
    title: str,
    link: str,
    published_at: datetime | None,
) -> RawItem:
    return RawItem(
        id=id_,
        source_id=source_id,
        raw_id=id_.split(":", 1)[-1],
        title=title,
        link=link,
        summary=None,
        published_at=published_at,
        extra={},
    )


def test_rule_filter_include_exclude_keywords_and_sort():
    now = datetime.now(timezone.utc)
    items = [
        _raw(
            id_="s1:a",
            source_id="s1",
            title="AI 发布新模型",
            link="https://x.com/a",
            published_at=now - timedelta(hours=1),
        ),
        _raw(
            id_="s2:b",
            source_id="s2",
            title="娱乐八卦 新闻",
            link="https://x.com/b",
            published_at=now - timedelta(hours=2),
        ),
        _raw(
            id_="s3:c",
            source_id="s3",
            title="AI 不是八卦",
            link="https://x.com/c",
            published_at=now - timedelta(hours=3),
        ),
    ]

    cfg = FilterConfig(
        strategy="rule",
        include_keywords=["AI"],
        exclude_keywords=["八卦"],
        max_age_hours=None,
        sort_by="published_at",
        order="desc",
    )

    out = filter_rule_and_sort(items, cfg)
    # include=AI -> 保留 a、c；exclude=八卦 -> c 不含八卦，a/c 都保留
    assert [x.link for x in out] == ["https://x.com/a", "https://x.com/c"]


def test_rule_filter_allowed_sources():
    now = datetime.now(timezone.utc)
    items = [
        _raw(
            id_="s1:a",
            source_id="s1",
            title="AI",
            link="https://x.com/a",
            published_at=now - timedelta(hours=1),
        ),
        _raw(
            id_="s2:b",
            source_id="s2",
            title="AI",
            link="https://x.com/b",
            published_at=now - timedelta(hours=1),
        ),
    ]
    cfg = FilterConfig(
        strategy="rule",
        allowed_sources=["s2"],
        max_age_hours=None,
        sort_by="published_at",
        order="asc",
    )
    out = filter_rule_and_sort(items, cfg)
    assert [x.link for x in out] == ["https://x.com/b"]


def test_rule_filter_max_age_hours_requires_published_at():
    now = datetime.now(timezone.utc)
    items = [
        _raw(
            id_="s1:a",
            source_id="s1",
            title="AI",
            link="https://x.com/a",
            published_at=now - timedelta(hours=1),
        ),
        _raw(
            id_="s2:b",
            source_id="s2",
            title="AI",
            link="https://x.com/b",
            published_at=None,
        ),
        _raw(
            id_="s3:c",
            source_id="s3",
            title="AI",
            link="https://x.com/c",
            published_at=now - timedelta(hours=100),
        ),
    ]
    cfg = FilterConfig(
        strategy="rule",
        max_age_hours=24,
        sort_by="published_at",
        order="desc",
    )
    out = filter_rule_and_sort(items, cfg)
    # max_age_hours=24: 保留 a；b 因 published_at=None 采用“宽松策略”保留；c 过旧被丢弃
    assert [x.link for x in out] == ["https://x.com/a", "https://x.com/b"]

