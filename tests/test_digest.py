"""单元测试：digest.template 早报生成。"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from app.config import DigestConfig
from app.digest import generate_digest
from app.digest.agent import _build_items_payload
from app.models import RawItem


def _raw(*, source_id: str, raw_id: str, title: str, link: str, summary: str | None = None, published_at=None, extra=None) -> RawItem:
    return RawItem(
        id=f"{source_id}:{raw_id}",
        source_id=source_id,
        raw_id=raw_id,
        title=title,
        link=link,
        summary=summary,
        published_at=published_at,
        extra=extra or {},
    )


def test_template_title_and_group_by_source():
    items = [
        _raw(
            source_id="s1",
            raw_id="r1",
            title="T1",
            link="https://x.com/1",
            summary="S1",
            published_at=datetime.now(timezone.utc) - timedelta(hours=1),
        ),
        _raw(
            source_id="s2",
            raw_id="r2",
            title="T2",
            link="https://x.com/2",
            summary=None,
            published_at=datetime.now(timezone.utc) - timedelta(hours=2),
        ),
    ]

    cfg = DigestConfig(
        strategy="template",
        title_template="每日早报 {{date}}",
        max_items=50,
        group_by="source",
    )

    digest = generate_digest(items, cfg)
    assert digest.title.startswith("每日早报 ")
    assert len(digest.sections) == 2
    names = {s.name for s in digest.sections}
    assert names == {"s1", "s2"}
    md = digest.rendered.markdown or ""
    assert "# " in md
    assert "## s1" in md
    assert "[T1](https://x.com/1)" in md
    assert "T2" in md


def test_template_max_items_truncation():
    items = [
        _raw(source_id="s1", raw_id="r1", title="T1", link="https://x.com/1"),
        _raw(source_id="s1", raw_id="r2", title="T2", link="https://x.com/2"),
        _raw(source_id="s1", raw_id="r3", title="T3", link="https://x.com/3"),
    ]
    cfg = DigestConfig(strategy="template", title_template="X {{date}}", max_items=2, group_by="none")
    digest = generate_digest(items, cfg)
    assert len(digest.sections) == 1
    assert len(digest.sections[0].items) == 2


def test_template_group_by_none_placeholder_when_no_items():
    cfg = DigestConfig(strategy="template", title_template="X {{date}}", max_items=50, group_by="none")
    digest = generate_digest([], cfg)
    assert len(digest.sections) == 1
    assert digest.sections[0].name == "All"
    assert digest.sections[0].items == []
    md = digest.rendered.markdown or ""
    assert "没有匹配的新内容" in md


def test_agent_payload_omits_description_by_default():
    items = [
        _raw(
            source_id="s1",
            raw_id="r1",
            title="AI 新闻",
            link="https://x.com/1",
            summary="很长很长的描述",
        )
    ]
    payload = _build_items_payload(items, 10)
    assert payload == [{"source": "s1", "title": "AI 新闻", "link": "https://x.com/1"}]


def test_agent_payload_can_include_description():
    items = [
        _raw(
            source_id="s1",
            raw_id="r1",
            title="AI 新闻",
            link="https://x.com/1",
            summary="abcdef",
        )
    ]
    payload = _build_items_payload(items, 10, include_summary=True, max_summary_chars=3)
    assert payload == [
        {
            "source": "s1",
            "title": "AI 新闻",
            "link": "https://x.com/1",
            "description": "abc",
        }
    ]


def test_agent_caps_headline_items(monkeypatch):
    import app.digest.agent as agent_mod

    def _fake_call(**kwargs):
        _ = kwargs
        items = [{"title": f"头条{i}", "link": f"https://x.com/{i}"} for i in range(7)]
        return (
            '{"title":"每日早报 2026-04-08","sections":[{"name":"📰 今日头条","items":'
            + str(items).replace("'", '"')
            + '}],"rendered":{"html":"<html></html>"}}'
        )

    monkeypatch.setattr(agent_mod, "call_minimax_chat", _fake_call)

    cfg = DigestConfig.model_validate(
        {
            "strategy": "agent",
            "title_template": "每日早报 {{date}}",
            "group_by": "source",
            "max_items": 50,
            "agent": {
                "endpoint": "https://api.minimaxi.com/v1/text/chatcompletion_v2",
                "api_key": "k",
                "model": "MiniMax-M2.7",
                "constraints": "x",
                "output_format": "rendered",
                "timeout_seconds": 60,
                "max_input_items": 50,
            },
        }
    )
    digest = generate_digest(
        [_raw(source_id="s1", raw_id="r1", title="t", link="https://x.com/1")],
        cfg,
    )
    assert len(digest.sections) == 1
    assert digest.sections[0].name == "📰 今日头条"
    assert len(digest.sections[0].items) == 5
