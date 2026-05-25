"""webpaper 渲染与发布的单元测试。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models import Digest, RawItem, RenderedDigest, Section
from app.web import render_paper
from app.web.paper import render_archive
from app.web.publish import publish_paper


def _sample_digest() -> Digest:
    now = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)
    return Digest(
        id="t",
        title="每日早报 2026-05-26",
        generated_at=now.isoformat(),
        sections=[
            Section(name="🌤️ 今日天气", text="多云转晴，18°C。\n出门带件薄外套。"),
            Section(
                name="📰 今日头条",
                items=[
                    RawItem(id="1", source_id="agent", raw_id="1", title="重大突破：某模型登顶",
                            link="https://example.com/a"),
                ],
            ),
            Section(
                name="🤖 AI与技术",
                items=[
                    RawItem(id="2", source_id="agent", raw_id="2", title="开源新模型发布",
                            link="https://news.ycombinator.com/x"),
                ],
            ),
        ],
        rendered=RenderedDigest(),
    )


def test_render_paper_contains_core_elements():
    html = render_paper(_sample_digest())
    assert "<!DOCTYPE html>" in html
    assert "每日早报 2026-05-26" in html
    assert "今日头条" in html and "AI与技术" in html
    # 天气版面用 text 渲染，换行转 <br>
    assert "多云转晴" in html and "<br>" in html
    # 头条作为 lead 渲染
    assert 'class="lead"' in html
    # 链接与来源域名
    assert "https://example.com/a" in html
    assert "news.ycombinator.com" in html
    # 报头日期（星期二）
    assert "星期二" in html


def test_render_paper_escapes_html():
    d = _sample_digest()
    d.sections[1].items[0].title = "<script>alert(1)</script>"
    html = render_paper(d)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_archive_lists_entries():
    html = render_archive([("2026-05-26", "papers/2026-05-26.html")])
    assert "2026-05-26 早报" in html
    assert "papers/2026-05-26.html" in html


def test_publish_writes_files_without_git(tmp_path):
    out = tmp_path / "site"
    res = publish_paper(_sample_digest(), output_dir=str(out), git_publish=False)
    assert res.page_path.exists()
    assert res.index_path.exists() and res.index_path.name == "index.html"
    assert res.archive_path.exists()
    assert res.git_pushed is False
    # dated 文件按日期命名
    assert (out / "papers" / "2026-05-26.html").exists()
    # index 含内容，archive 链接到 dated 文件
    assert "每日早报 2026-05-26" in res.index_path.read_text(encoding="utf-8")
    assert "2026-05-26.html" in res.archive_path.read_text(encoding="utf-8")
