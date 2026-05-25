"""
拟物（skeuomorphism）多版报纸网页渲染。

输入 Digest（结构化 sections：版面名 + 条目 title/link/summary，天气版面用 text），
输出自包含 HTML：头版（masthead + 天气栏 + 头条导语 + 次条 + 本期导读）+ 各版面内页
（标题/来源/摘要/阅读全文，多栏），纸张质感 + 轻量交互（鼠标视差、悬浮抬起、翻折纸角），
无第三方依赖，含打印样式，适合 GitHub Pages。
"""

from __future__ import annotations

import html
from datetime import datetime
from urllib.parse import urlparse

from app.models import Digest, Section

_WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def _esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def _domain(url: str | None) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).netloc
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _parse_dt(generated_at: str | None) -> datetime:
    if generated_at:
        try:
            return datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now()


def _date_line(dt: datetime) -> str:
    return f"{dt.year}年{dt.month}月{dt.day}日　{_WEEKDAY_CN[dt.weekday()]}"


def _is_weather(name: str) -> bool:
    return "天气" in name


def _is_headline(name: str) -> bool:
    return "头条" in name


def _is_epic(name: str) -> bool:
    return "Epic" in name or "epic" in name


def _byline(it) -> str:
    extra = it.extra if isinstance(it.extra, dict) else {}
    src = extra.get("source_name") or _domain(it.link)
    t = extra.get("time")
    bits = [b for b in (src, t) if b]
    return "　·　".join(_esc(str(b)) for b in bits)


# ---------------------------------------------------------------- CSS / JS

_CSS = """
:root{
  --paper:#f3ece0; --paper2:#efe7d8; --ink:#1c1a17; --muted:#5a5347;
  --rule:#2a2722; --accent:#7a1f1a; --link:#243b6b;
}
*{box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{margin:0;padding:40px 16px 90px;min-height:100vh;
  background:#2f2a25;
  background-image:radial-gradient(circle at 30% 10%, #3a342d 0%, #221e1a 75%);
  font-family:"Songti SC","Noto Serif SC","Source Han Serif SC",STSong,SimSun,Georgia,"Times New Roman",serif;
  color:var(--ink);-webkit-font-smoothing:antialiased;perspective:2000px;}
.stage{max-width:1060px;margin:0 auto;perspective:2000px;}

.sheet{position:relative;background:var(--paper);
  background-image:
    radial-gradient(circle at 18% 10%, rgba(255,255,255,.45), transparent 42%),
    radial-gradient(circle at 84% 92%, rgba(120,90,50,.10), transparent 46%),
    url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.05'/></svg>");
  padding:46px 52px 56px;border-radius:2px;margin:0 auto 46px;
  box-shadow:0 2px 0 #d9cfba, 0 30px 60px rgba(0,0,0,.55), inset 0 0 60px rgba(120,90,50,.10);
  transform-style:preserve-3d;transition:transform .12s ease-out;will-change:transform;}
.sheet::before,.sheet::after{content:"";position:absolute;inset:0;background:var(--paper2);
  border-radius:2px;z-index:-1;box-shadow:0 18px 40px rgba(0,0,0,.4);}
.sheet::before{transform:translate(6px,8px) rotate(.4deg);}
.sheet::after{transform:translate(11px,15px) rotate(-.6deg);}

.peel{position:absolute;top:0;right:0;width:50px;height:50px;cursor:pointer;z-index:5;
  background:linear-gradient(225deg, var(--paper) 46%, #cdbfa3 50%, #7c6f57 60%, rgba(0,0,0,.25) 100%);
  box-shadow:-3px 3px 8px rgba(0,0,0,.25);clip-path:polygon(100% 0,0 0,100% 100%);
  transition:width .18s,height .18s,box-shadow .18s;}
.peel:hover{width:80px;height:80px;box-shadow:-6px 6px 14px rgba(0,0,0,.35);}

/* 报头 */
.masthead{text-align:center;border-bottom:4px double var(--rule);padding-bottom:14px;}
.masthead .corners{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);
  font-family:system-ui,sans-serif;letter-spacing:1px;text-transform:uppercase;}
.title{font-size:clamp(40px,7vw,78px);line-height:1.02;margin:.06em 0 .04em;letter-spacing:.06em;
  font-weight:700;text-shadow:0 1px 0 rgba(255,255,255,.5);}
.subtitle{font-size:13px;color:var(--muted);font-family:system-ui,sans-serif;letter-spacing:.35em;text-transform:uppercase;}
.dateline{display:flex;justify-content:center;gap:18px;margin-top:10px;font-size:13px;color:var(--muted);
  border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);padding:6px 0;font-family:system-ui,sans-serif;}

.weatherbar{margin:16px 0 4px;padding:10px 16px;border:1px solid #c9bfa0;border-left:4px solid var(--accent);
  background:rgba(255,255,255,.35);font-size:14px;line-height:1.65;}
.weatherbar b{font-family:system-ui,sans-serif;color:var(--accent);letter-spacing:.1em;}

/* 头版网格：头条 + 导读 */
.frontgrid{display:grid;grid-template-columns:1fr 270px;gap:34px;margin-top:18px;}
.lead-label{font-size:13px;letter-spacing:.4em;color:var(--accent);font-family:system-ui,sans-serif;
  text-transform:uppercase;margin-bottom:6px;}
.lead-main{display:block;text-decoration:none;color:var(--ink);padding-bottom:14px;border-bottom:2px solid var(--rule);margin-bottom:14px;}
.lead-main .lt{font-size:clamp(28px,4.6vw,46px);line-height:1.14;font-weight:700;}
.lead-main .standfirst{font-size:17px;line-height:1.7;color:#34302a;margin-top:10px;font-style:normal;}
.lead-main .by{font-size:12px;color:var(--muted);font-family:system-ui,sans-serif;margin-top:8px;}
.lead-rest .hl{display:block;text-decoration:none;color:var(--ink);padding:10px 0;border-top:1px dotted #b9ac90;}
.lead-rest .hl .t{font-size:19px;line-height:1.3;font-weight:700;}
.lead-rest .hl .s{display:block;font-size:13.5px;color:#4a443b;line-height:1.55;margin-top:3px;}

.index{border:1px solid var(--rule);background:rgba(255,255,255,.28);padding:14px 16px;height:max-content;}
.index h3{margin:0 0 10px;font-size:16px;border-bottom:1px solid var(--rule);padding-bottom:6px;letter-spacing:.1em;}
.index ul{list-style:none;margin:0;padding:0;}
.index li{margin:0 0 7px;}
.index a{display:flex;justify-content:space-between;gap:8px;text-decoration:none;color:var(--ink);font-size:14px;}
.index a:hover{color:var(--accent);}
.index a .pg{color:var(--muted);font-family:system-ui,sans-serif;white-space:nowrap;}

/* 内页 */
.pagehead{display:flex;align-items:baseline;justify-content:space-between;border-bottom:3px double var(--rule);
  padding-bottom:8px;margin-bottom:14px;}
.pagehead h2{margin:0;font-size:26px;letter-spacing:.06em;}
.pagehead .ed{font-size:12px;color:var(--muted);font-family:system-ui,sans-serif;letter-spacing:.1em;}
.columns{column-width:320px;column-gap:36px;column-rule:1px solid #cfc2a6;}
.art{break-inside:avoid;display:block;text-decoration:none;color:var(--ink);padding:12px;margin:0 -12px 8px;
  border-bottom:1px solid #d7cab0;border-radius:4px;
  transition:transform .12s,box-shadow .12s,background .12s;}
.art:hover{background:rgba(255,255,255,.55);transform:translateY(-2px);box-shadow:0 6px 16px rgba(0,0,0,.12);}
.art .at{font-size:18px;line-height:1.34;font-weight:700;}
.art:hover .at{text-decoration:underline;text-decoration-color:var(--accent);}
.art .by{font-size:11.5px;color:var(--muted);font-family:system-ui,sans-serif;margin:4px 0 6px;letter-spacing:.03em;}
.art .as{font-size:14px;line-height:1.66;color:#34302a;margin:0;text-align:justify;}
.art .more{display:inline-block;margin-top:6px;font-size:12px;color:var(--link);font-family:system-ui,sans-serif;}

/* Epic 卡片 */
.epic{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;}
.epic a{text-decoration:none;color:inherit;border:1px solid #cfc2a6;border-radius:8px;overflow:hidden;background:rgba(255,255,255,.45);}
.epic img{width:100%;height:150px;object-fit:cover;display:block;}
.epic .ec{padding:10px 12px;}
.epic .et{font-weight:700;font-size:15px;}
.epic .em{font-size:12px;color:var(--muted);font-family:system-ui,sans-serif;margin-top:5px;}

.colophon{margin-top:26px;padding-top:12px;border-top:4px double var(--rule);display:flex;justify-content:space-between;
  font-size:12px;color:var(--muted);font-family:system-ui,sans-serif;letter-spacing:.06em;}
.colophon a{color:var(--link);text-decoration:none;}
.colophon a:hover{text-decoration:underline;}

@media (max-width:760px){
  body{padding:18px 8px 50px;}
  .sheet{padding:26px 20px 36px;}
  .frontgrid{grid-template-columns:1fr;}
  .columns{column-width:auto;column-count:1;}
}
@media (prefers-reduced-motion:reduce){.sheet{transition:none!important;}}
@media print{
  body{background:#fff;padding:0;perspective:none;}
  .sheet{box-shadow:none;margin:0;page-break-after:always;}
  .sheet::before,.sheet::after,.peel{display:none;}
}
"""

_JS = """
(function(){
  var reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion:reduce)').matches;
  var fine=window.matchMedia&&window.matchMedia('(pointer:fine)').matches;
  document.querySelectorAll('.sheet').forEach(function(sheet){
    var peel=sheet.querySelector('.peel');
    if(peel) peel.addEventListener('click',function(){window.scrollTo({top:0,behavior:'smooth'});});
    if(reduce||!fine) return;
    sheet.addEventListener('mousemove',function(e){
      var r=sheet.getBoundingClientRect();
      var cx=(e.clientX-(r.left+r.width/2))/r.width, cy=(e.clientY-(r.top+r.height/2))/r.height;
      sheet.style.transform='rotateY('+(cx*2.4).toFixed(2)+'deg) rotateX('+(-cy*2).toFixed(2)+'deg)';
    });
    sheet.addEventListener('mouseleave',function(){sheet.style.transform='rotateY(0) rotateX(0)';});
  });
})();
"""


# ---------------------------------------------------------------- pieces


def _render_article(it, show_summary: bool) -> str:
    by = _byline(it)
    summ = f'<p class="as">{_esc(it.summary)}</p>' if (show_summary and it.summary) else ""
    return (
        f'<a class="art" href="{_esc(it.link)}" target="_blank" rel="noopener">'
        f'<span class="at">{_esc(it.title)}</span>'
        + (f'<div class="by">{by}</div>' if by else "")
        + summ
        + '<span class="more">阅读全文 →</span></a>'
    )


def _render_epic_page(sec: Section, idx: int, total: int, archive_href: str) -> str:
    cards = ""
    for it in sec.items:
        extra = it.extra if isinstance(it.extra, dict) else {}
        cover = extra.get("cover") or ""
        end = extra.get("free_end") or ""
        price = extra.get("original_price_desc") or ""
        badge = "🎁 免费领取中" if extra.get("is_free_now") else "⏳ 即将免费"
        cards += (
            f'<a href="{_esc(it.link)}" target="_blank" rel="noopener">'
            + (f'<img src="{_esc(cover)}" alt="">' if cover else "")
            + f'<div class="ec"><div class="et">{_esc(it.title)}</div>'
            f'<div class="em">{badge}　截止 {_esc(end)}　<s>{_esc(price)}</s> 免费</div></div></a>'
        )
    return _wrap_page(
        sec.name, idx, total,
        f'<div class="epic">{cards}</div>', archive_href,
    )


def _wrap_page(name: str, idx: int, total: int, inner: str, archive_href: str) -> str:
    return (
        f'<div class="sheet" id="page-{idx}"><div class="peel" title="回到顶部"></div>'
        f'<div class="pagehead"><h2>{_esc(name)}</h2><span class="ed">第 {idx} 版 / 共 {total} 版</span></div>'
        f'{inner}'
        f'<div class="colophon"><a href="#page-1">← 返回头版</a><a href="{_esc(archive_href)}">往期 →</a></div></div>'
    )


def _render_front(
    *, title, masthead_en, issue, dt, weather: Section | None,
    headline: Section | None, index_entries, total, archive_href, show_summary,
) -> str:
    wbar = ""
    if weather and weather.text:
        wbar = f'<div class="weatherbar"><b>{_esc(weather.name)}</b>　{_esc(weather.text).splitlines()[0] if weather.text else ""}</div>'

    lead = ""
    if headline and headline.items:
        first = headline.items[0]
        rest = headline.items[1:]
        standfirst = f'<p class="standfirst">{_esc(first.summary)}</p>' if (show_summary and first.summary) else ""
        by = _byline(first)
        lead = (
            '<div class="lead"><div class="lead-label">今日头条</div>'
            f'<a class="lead-main" href="{_esc(first.link)}" target="_blank" rel="noopener">'
            f'<span class="lt">{_esc(first.title)}</span>{standfirst}'
            + (f'<div class="by">{by}</div>' if by else "")
            + '</a><div class="lead-rest">'
        )
        for it in rest:
            teaser = f'<span class="s">{_esc(it.summary)}</span>' if (show_summary and it.summary) else ""
            lead += (
                f'<a class="hl" href="{_esc(it.link)}" target="_blank" rel="noopener">'
                f'<span class="t">{_esc(it.title)}</span>{teaser}</a>'
            )
        lead += "</div></div>"
    else:
        lead = '<div class="lead"><div class="lead-label">今日头条</div><p>今日暂无头条。</p></div>'

    idx_items = "".join(
        f'<li><a href="#page-{pg}"><span>{_esc(nm)}</span><span class="pg">第 {pg} 版</span></a></li>'
        for nm, pg in index_entries
    )
    index = f'<aside class="index"><h3>本期导读</h3><ul>{idx_items}</ul></aside>'

    return (
        '<div class="sheet front" id="page-1"><div class="peel" title="回到顶部"></div>'
        '<header class="masthead">'
        f'<div class="corners"><span>{_esc(issue)}</span><span>AI 编纂 · 仅供阅读</span></div>'
        f'<h1 class="title">{_esc(title)}</h1><div class="subtitle">{_esc(masthead_en)}</div>'
        f'<div class="dateline"><span>{_esc(_date_line(dt))}</span></div></header>'
        f'{wbar}<div class="frontgrid">{lead}{index}</div>'
        f'<div class="colophon"><span>第 1 版 · 头版</span><a href="{_esc(archive_href)}">查看往期 →</a></div></div>'
    )


def render_paper(
    digest: Digest,
    *,
    masthead_en: str = "THE DAILY DISPATCH",
    archive_href: str = "archive.html",
    issue_label: str | None = None,
    multi_page: bool = True,
    show_summaries: bool = True,
) -> str:
    """将 Digest 渲染为拟物多版报纸 HTML。"""
    dt = _parse_dt(digest.generated_at)
    title = digest.title or "每日早报"
    issue = issue_label or f"第 {dt.strftime('%Y%m%d')} 期"

    weather = next((s for s in digest.sections if _is_weather(s.name) and s.text), None)
    headline = next((s for s in digest.sections if _is_headline(s.name) and s.items), None)
    inner = [
        s for s in digest.sections
        if s is not weather and s is not headline and (s.items or s.text)
    ]

    if not multi_page:
        # 单版：头条 + 全部版面塞进一张大报
        body = _render_single(title, masthead_en, issue, dt, weather, headline, inner, archive_href, show_summaries)
        return _document(title, masthead_en, body)

    # 多版：头版 + 每个版面一页
    total = 1 + len(inner)
    index_entries = [(s.name, 2 + i) for i, s in enumerate(inner)]
    pages = [
        _render_front(
            title=title, masthead_en=masthead_en, issue=issue, dt=dt, weather=weather,
            headline=headline, index_entries=index_entries, total=total,
            archive_href=archive_href, show_summary=show_summaries,
        )
    ]
    for i, sec in enumerate(inner):
        idx = 2 + i
        if _is_epic(sec.name):
            pages.append(_render_epic_page(sec, idx, total, archive_href))
        else:
            arts = "".join(_render_article(it, show_summaries) for it in sec.items)
            body = f'<div class="columns">{arts}</div>' if arts else (f'<p>{_esc(sec.text or "")}</p>')
            pages.append(_wrap_page(sec.name, idx, total, body, archive_href))
    return _document(title, masthead_en, "".join(pages))


def _render_single(title, masthead_en, issue, dt, weather, headline, inner, archive_href, show_summaries) -> str:
    wbar = ""
    if weather and weather.text:
        wbar = f'<div class="weatherbar"><b>{_esc(weather.name)}</b>　{_esc(weather.text).splitlines()[0]}</div>'
    secs = ""
    ordered = ([headline] if headline else []) + inner
    for sec in ordered:
        if not sec:
            continue
        arts = "".join(_render_article(it, show_summaries) for it in sec.items)
        secs += f'<section><div class="pagehead"><h2>{_esc(sec.name)}</h2></div><div class="columns">{arts}</div></section>'
    return (
        '<div class="sheet" id="page-1"><div class="peel"></div>'
        '<header class="masthead">'
        f'<div class="corners"><span>{_esc(issue)}</span><span>AI 编纂</span></div>'
        f'<h1 class="title">{_esc(title)}</h1><div class="subtitle">{_esc(masthead_en)}</div>'
        f'<div class="dateline"><span>{_esc(_date_line(dt))}</span></div></header>'
        f'{wbar}{secs}'
        f'<div class="colophon"><span>{_esc(_date_line(dt))}</span><a href="{_esc(archive_href)}">往期 →</a></div></div>'
    )


def _document(title: str, masthead_en: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="stage">
{body}
</div>
<script>{_JS}</script>
</body>
</html>
"""


def render_archive(entries: list[tuple[str, str]], *, masthead_en: str = "ARCHIVE") -> str:
    """生成往期索引页。entries: [(date_str, href), ...]，新到旧。"""
    items = "".join(
        f'<a class="art" href="{_esc(href)}"><span class="at">{_esc(d)} 早报</span>'
        f'<span class="by">{_esc(href)}</span></a>'
        for d, href in entries
    )
    if not items:
        items = "<p>暂无往期</p>"
    body = (
        '<div class="sheet"><div class="peel"></div>'
        '<header class="masthead"><h1 class="title">往期早报</h1>'
        f'<div class="subtitle">{_esc(masthead_en)}</div></header>'
        f'<div class="columns" style="margin-top:18px;">{items}</div>'
        '<div class="colophon"><a href="index.html">← 返回今日</a><span></span></div></div>'
    )
    return _document("早报 · 往期索引", masthead_en, body)


__all__ = ["render_paper", "render_archive"]
