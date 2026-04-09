"""单元测试：models 模块（RawItem, Digest, Section, RenderedDigest）。"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.models import Digest, RawItem, RenderedDigest, Section


def test_raw_item_minimal():
    item = RawItem(
        id="a1",
        source_id="rss-1",
        raw_id="guid-1",
        title="Title",
        link="https://example.com/1",
    )
    assert item.summary is None
    assert item.published_at is None
    assert item.extra == {}


def test_raw_item_with_published_at_str():
    item = RawItem(
        id="a2",
        source_id="rss-1",
        raw_id="guid-2",
        title="T",
        link="https://example.com/2",
        published_at="2025-02-15T08:00:00",
    )
    assert item.published_at == datetime(2025, 2, 15, 8, 0, 0)


def test_raw_item_with_published_at_iso_z():
    item = RawItem(
        id="a3",
        source_id="rss-1",
        raw_id="guid-3",
        title="T",
        link="https://example.com/3",
        published_at="2025-02-15T08:00:00Z",
    )
    assert item.published_at is not None


def test_section():
    sec = Section(name="科技", items=[])
    assert sec.name == "科技"
    assert sec.items == []


def test_rendered_digest():
    r = RenderedDigest(markdown="# Hello")
    assert r.text is None
    assert r.markdown == "# Hello"
    assert r.html is None


def test_digest():
    d = Digest(
        id="d1",
        title="每日早报 2025-02-15",
        generated_at="2025-02-15T07:00:00",
        sections=[Section(name="科技", items=[])],
        rendered=RenderedDigest(markdown="# 早报"),
    )
    assert d.id == "d1"
    assert len(d.sections) == 1
    assert d.rendered.markdown == "# 早报"


def test_digest_default_rendered():
    d = Digest(
        id="d2",
        title="T",
        generated_at="2025-02-15T07:00:00",
    )
    assert d.sections == []
    assert d.rendered.text is None and d.rendered.markdown is None
