"""单元测试：dedup 模块。"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.dedup import deduplicate
from app.models import RawItem


def _item(
    *,
    source_id: str,
    raw_id: str,
    title: str,
    link: str | None,
) -> RawItem:
    return RawItem(
        id=f"{source_id}:{raw_id}",
        source_id=source_id,
        raw_id=raw_id,
        title=title,
        link=link or "",
        published_at=datetime(2025, 2, 15, 8, 0, 0),
        summary=None,
        extra={},
    )


def test_deduplicate_by_link_stable_and_normalize_trailing_slash():
    a1 = _item(source_id="s1", raw_id="r1", title="A1", link="https://x.com/a/")
    a2 = _item(source_id="s2", raw_id="r2", title="A2", link="https://x.com/a")
    a3 = _item(source_id="s3", raw_id="r3", title="A3", link="https://x.com/b")

    out = deduplicate([a1, a2, a3], key="link")
    assert [x.title for x in out] == ["A1", "A3"]


def test_deduplicate_by_link_remove_fragment():
    a1 = _item(source_id="s1", raw_id="r1", title="A1", link="https://x.com/a#section1")
    a2 = _item(source_id="s2", raw_id="r2", title="A2", link="https://x.com/a#section2")
    out = deduplicate([a1, a2], key="link")
    assert [x.title for x in out] == ["A1"]


def test_deduplicate_by_raw_id():
    a1 = _item(source_id="s1", raw_id="same", title="A1", link="https://x.com/a")
    a2 = _item(source_id="s2", raw_id="same", title="A2", link="https://x.com/b")
    out = deduplicate([a1, a2], key="raw_id")
    assert [x.title for x in out] == ["A1"]


def test_deduplicate_empty():
    assert deduplicate([], key="link") == []


def test_deduplicate_link_empty_fallback_to_raw_id():
    # crawler/api 可能出现 link 为空的情况：实现里会降级到 raw_id 去重
    a1 = _item(source_id="s1", raw_id="r1", title="A1", link=None)
    a2 = _item(source_id="s2", raw_id="r2", title="A2", link=None)
    out = deduplicate([a1, a2], key="link")
    assert [x.title for x in out] == ["A1", "A2"]

