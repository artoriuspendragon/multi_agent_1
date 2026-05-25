"""webpaper 渲染、邮件渲染、agent 提示词与发布的单元测试。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import DEFAULT_DIGEST_SECTIONS, DigestAgentConfig
from app.digest.agent import _build_system_prompt
from app.digest.render import render_email_html
from app.models import Digest, RawItem, RenderedDigest, Section
from app.web import render_paper
from app.web.paper import render_archive
from app.web.publish import publish_paper


def _it(t, l, s=None, src=None):
    extra = {"source_name": src} if src else {}
    return RawItem(id=l, source_id="agent", raw_id=l, title=t, link=l, summary=s, extra=extra)


def _sample_digest() -> Digest:
    now = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)
    return Digest(
        id="t",
        title="每日早报 2026-05-26",
        generated_at=now.isoformat(),
        sections=[
            Section(name="🌤️ 今日天气", text="多云转晴，18°C。\n出门带件薄外套。"),
            Section(name="📰 今日头条", items=[
                _it("教皇发布首份 AI 通谕", "https://example.com/a", "教皇呼吁放缓 AI 发展并加强治理。", "梵蒂冈"),
                _it("某国领导人会谈", "https://example.com/b", "双方签署多项合作协议。"),
            ]),
            Section(name="🤖 AI与大模型", items=[
                _it("开源新模型发布", "https://news.ycombinator.com/x", "该模型在多项基准上领先，支持本地部署。", "HN"),
            ]),
            Section(name="🎮 游戏", items=[
                _it("某游戏融资破十亿", "https://www.yystv.cn/p/x", "开发十四年仍无发售日期。"),
            ]),
        ],
        rendered=RenderedDigest(),
    )


# ---------------- 网页（多版）----------------

def test_multipage_front_and_inner():
    html = render_paper(_sample_digest(), multi_page=True, show_summaries=True)
    assert "<!DOCTYPE html>" in html
    assert "每日早报 2026-05-26" in html
    assert "本期导读" in html
    assert 'class="lead"' in html
    assert "星期二" in html
    assert "第 2 版" in html
    assert "AI与大模型" in html and "游戏" in html
    assert "支持本地部署" in html
    assert "今日天气" in html and "多云转晴" in html


def test_summaries_can_be_hidden():
    html = render_paper(_sample_digest(), multi_page=True, show_summaries=False)
    assert "支持本地部署" not in html
    assert "AI与大模型" in html


def test_single_page_mode():
    html = render_paper(_sample_digest(), multi_page=False, show_summaries=True)
    assert "本期导读" not in html
    assert "AI与大模型" in html
    assert "支持本地部署" in html


def test_render_paper_escapes_html():
    d = _sample_digest()
    d.sections[2].items[0].title = "<script>alert(1)</script>"
    html = render_paper(d)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ---------------- 邮件 ----------------

def test_email_html_concise():
    html = render_email_html(_sample_digest())
    assert "每日早报 2026-05-26" in html
    assert "今日头条" in html and "AI与大模型" in html
    assert "https://news.ycombinator.com/x" in html
    assert "多云转晴" in html and "<br>" in html


# ---------------- agent 提示词 ----------------

def test_system_prompt_uses_config():
    cfg = DigestAgentConfig(
        endpoint="x", api_key="x", model="x", constraints="c",
        sections=DEFAULT_DIGEST_SECTIONS, headline_count=8, items_per_section=18,
        include_item_summary=True, summary_target_chars=140,
    )
    p = _build_system_prompt(cfg)
    assert "🤖 AI与大模型" in p and "💻 开发与编程" in p
    assert "最多 8 条" in p and "最多 18 条" in p
    assert "140 字" in p and "summary" in p


# ---------------- 发布 ----------------

def test_render_archive_lists_entries():
    html = render_archive([("2026-05-26", "papers/2026-05-26.html")])
    assert "2026-05-26 早报" in html
    assert "papers/2026-05-26.html" in html


def test_publish_writes_files_without_git(tmp_path):
    out = tmp_path / "site"
    res = publish_paper(_sample_digest(), output_dir=str(out), git_publish=False)
    assert res.page_path.exists() and res.index_path.name == "index.html"
    assert res.archive_path.exists() and res.git_pushed is False
    assert (out / "papers" / "2026-05-26.html").exists()
    assert "每日早报 2026-05-26" in res.index_path.read_text(encoding="utf-8")
