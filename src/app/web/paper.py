"""
拟物（skeuomorphism）报纸风格早报网页渲染。

输入 Digest（使用其结构化 sections：版面名 + 条目 title/link，天气版面用 text），
输出一个自包含的 HTML 页面：报纸大报（broadsheet）排版 + 纸张质感 + 轻量交互
（鼠标视差倾斜、文章悬浮抬起、可翻折的纸角），无第三方 JS 依赖，适合 GitHub Pages。
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
    return f"{dt.year}年{dt.month}月{dt.day}日　{_WEEKDAY_CN[dt.weekday()]}　农历见黄历"


def _is_weather(name: str) -> bool:
    return "天气" in name


def _is_headline(name: str) -> bool:
    return "头条" in name


# ---------------------------------------------------------------- CSS / JS

_CSS = """
:root{
  --paper:#f3ece0; --paper2:#efe7d8; --ink:#1c1a17; --muted:#5a5347;
  --rule:#2a2722; --accent:#7a1f1a; --link:#243b6b;
}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;}
body{
  background:#2f2a25;
  background-image:
    radial-gradient(circle at 30% 20%, #3a342d 0%, #221e1a 70%),
    repeating-linear-gradient(90deg, rgba(0,0,0,.06) 0 2px, transparent 2px 6px);
  min-height:100vh; padding:40px 16px 80px;
  font-family:"Songti SC","Noto Serif SC","Source Han Serif SC",STSong,SimSun,Georgia,"Times New Roman",serif;
  color:var(--ink); -webkit-font-smoothing:antialiased;
  perspective:1800px;
}
.stage{max-width:1040px;margin:0 auto;perspective:1800px;}
.sheet{
  position:relative; background:var(--paper);
  background-image:
    radial-gradient(circle at 18% 12%, rgba(255,255,255,.45), transparent 40%),
    radial-gradient(circle at 82% 88%, rgba(120,90,50,.10), transparent 45%),
    url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.05'/></svg>");
  padding:48px 52px 60px; border-radius:2px;
  box-shadow:0 2px 0 #d9cfba, 0 30px 60px rgba(0,0,0,.55), inset 0 0 60px rgba(120,90,50,.10);
  transform-style:preserve-3d; transition:transform .12s ease-out;
  will-change:transform;
}
/* 叠在下方的“纸堆”错觉 */
.sheet::before,.sheet::after{
  content:""; position:absolute; inset:0; background:var(--paper2);
  border-radius:2px; z-index:-1; box-shadow:0 18px 40px rgba(0,0,0,.4);
}
.sheet::before{transform:translate(6px,8px) rotate(.5deg);}
.sheet::after{transform:translate(11px,15px) rotate(-.7deg);}

/* 可翻折的纸角 */
.peel{
  position:absolute; top:0; right:0; width:54px; height:54px; cursor:pointer; z-index:5;
  background:linear-gradient(225deg, var(--paper) 46%, #cdbfa3 50%, #7c6f57 60%, rgba(0,0,0,.25) 100%);
  box-shadow:-3px 3px 8px rgba(0,0,0,.25);
  clip-path:polygon(100% 0, 0 0, 100% 100%);
  transition:width .18s ease, height .18s ease, box-shadow .18s ease;
}
.peel:hover{width:84px;height:84px;box-shadow:-6px 6px 14px rgba(0,0,0,.35);}
.peel-tip{position:absolute;top:6px;right:6px;font-size:10px;color:var(--muted);
  font-family:system-ui,sans-serif;letter-spacing:.5px;z-index:6;opacity:.7;}

/* 报头 */
.masthead{text-align:center;border-bottom:4px double var(--rule);padding-bottom:14px;}
.masthead .corners{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);
  font-family:system-ui,sans-serif;letter-spacing:1px;text-transform:uppercase;}
.title{font-size:clamp(40px,7vw,76px);line-height:1.02;margin:.06em 0 .04em;letter-spacing:.06em;
  font-weight:700;text-shadow:0 1px 0 rgba(255,255,255,.5);}
.subtitle{font-size:13px;color:var(--muted);font-family:system-ui,sans-serif;letter-spacing:.35em;text-transform:uppercase;}
.dateline{display:flex;justify-content:center;gap:18px;align-items:center;margin-top:10px;
  font-size:13px;color:var(--muted);border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);
  padding:6px 0;font-family:system-ui,sans-serif;}

/* 天气小报头 */
.weather{margin:18px 0 6px;padding:12px 16px;border:1px solid #c9bfa0;border-left:4px solid var(--accent);
  background:rgba(255,255,255,.35);font-size:15px;line-height:1.7;}
.weather b{font-family:system-ui,sans-serif;letter-spacing:.1em;color:var(--accent);}

/* 头条 */
.lead{padding:20px 0 8px;border-bottom:2px solid var(--rule);column-span:all;}
.lead h2{font-size:13px;letter-spacing:.4em;color:var(--accent);margin:0 0 10px;
  font-family:system-ui,sans-serif;text-transform:uppercase;}
.lead .hl{display:block;text-decoration:none;color:var(--ink);padding:9px 0;border-top:1px dotted #b9ac90;}
.lead .hl:first-of-type{border-top:none;}
.lead .hl .t{font-size:clamp(22px,3.2vw,32px);line-height:1.18;font-weight:700;}
.lead .hl:first-of-type .t{font-size:clamp(28px,4.4vw,44px);}
.lead .hl .src{font-size:12px;color:var(--muted);font-family:system-ui,sans-serif;}

/* 正文多栏 */
.columns{margin-top:18px;column-width:300px;column-gap:34px;column-rule:1px solid #cfc2a6;}
.section{break-inside:avoid;margin:0 0 22px;}
.section > h3{font-size:19px;margin:0 0 8px;padding-bottom:6px;border-bottom:2px solid var(--rule);
  letter-spacing:.05em;}
.article{display:block;text-decoration:none;color:var(--ink);padding:8px 6px;margin:0 -6px;
  border-bottom:1px solid #d7cab0;border-radius:3px;transition:transform .12s ease, box-shadow .12s ease, background .12s ease;}
.article:last-child{border-bottom:none;}
.article:hover{background:rgba(255,255,255,.55);transform:translateY(-2px);
  box-shadow:0 6px 14px rgba(0,0,0,.12);}
.article .t{font-size:16px;line-height:1.45;font-weight:600;}
.article:hover .t{text-decoration:underline;text-decoration-color:var(--accent);}
.article .src{display:block;margin-top:3px;font-size:11.5px;color:var(--muted);
  font-family:system-ui,sans-serif;letter-spacing:.04em;}

.colophon{margin-top:30px;padding-top:14px;border-top:4px double var(--rule);text-align:center;
  font-size:12px;color:var(--muted);font-family:system-ui,sans-serif;letter-spacing:.08em;}
.colophon a{color:var(--link);text-decoration:none;}
.colophon a:hover{text-decoration:underline;}

@media (max-width:680px){
  body{padding:18px 8px 50px;}
  .sheet{padding:26px 20px 36px;}
  .columns{column-width:auto;column-count:1;}
}
@media (prefers-reduced-motion:reduce){
  .sheet{transition:none!important;}
}
"""

_JS = """
(function(){
  var sheet=document.querySelector('.sheet'), stage=document.querySelector('.stage');
  if(!sheet||!stage) return;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion:reduce)').matches;
  var fine = window.matchMedia && window.matchMedia('(pointer:fine)').matches;
  if(!reduce && fine){
    stage.addEventListener('mousemove', function(e){
      var r=sheet.getBoundingClientRect();
      var cx=(e.clientX-(r.left+r.width/2))/r.width;
      var cy=(e.clientY-(r.top+r.height/2))/r.height;
      sheet.style.transform='rotateY('+(cx*3.2).toFixed(2)+'deg) rotateX('+(-cy*2.6).toFixed(2)+'deg)';
    });
    stage.addEventListener('mouseleave', function(){ sheet.style.transform='rotateY(0) rotateX(0)'; });
  }
  var peel=document.querySelector('.peel');
  if(peel){ peel.addEventListener('click', function(){ window.scrollTo({top:0,behavior:'smooth'}); }); }
})();
"""


# ---------------------------------------------------------------- HTML pieces


def _render_lead(section: Section) -> str:
    rows = []
    for it in section.items:
        rows.append(
            f'<a class="hl" href="{_esc(it.link)}" target="_blank" rel="noopener">'
            f'<span class="t">{_esc(it.title)}</span>'
            f'<span class="src">— {_esc(_domain(it.link))}</span></a>'
        )
    return (
        '<div class="lead"><h2>{name}</h2>{rows}</div>'.format(
            name=_esc(section.name), rows="".join(rows)
        )
    )


def _render_weather(section: Section) -> str:
    return (
        f'<div class="weather"><b>{_esc(section.name)}</b><br>'
        f'{_esc(section.text).replace(chr(10), "<br>")}</div>'
    )


def _render_section(section: Section) -> str:
    arts = []
    for it in section.items:
        arts.append(
            f'<a class="article" href="{_esc(it.link)}" target="_blank" rel="noopener">'
            f'<span class="t">{_esc(it.title)}</span>'
            f'<span class="src">{_esc(_domain(it.link))}</span></a>'
        )
    if not arts:
        return ""
    return (
        f'<section class="section"><h3>{_esc(section.name)}</h3>{"".join(arts)}</section>'
    )


def render_paper(
    digest: Digest,
    *,
    masthead_en: str = "THE DAILY DISPATCH",
    archive_href: str = "archive.html",
    issue_label: str | None = None,
) -> str:
    """将 Digest 渲染为拟物报纸风格的完整 HTML 页面。"""
    dt = _parse_dt(digest.generated_at)
    title = digest.title or "每日早报"

    weather_html = ""
    lead_html = ""
    body_sections: list[str] = []

    for sec in digest.sections:
        if _is_weather(sec.name) and sec.text:
            weather_html = _render_weather(sec)
        elif _is_headline(sec.name) and sec.items:
            lead_html = _render_lead(sec)
        else:
            html_sec = _render_section(sec)
            if html_sec:
                body_sections.append(html_sec)

    if not lead_html and not body_sections and not weather_html:
        body_sections.append('<section class="section"><h3>本期暂无内容</h3></section>')

    issue = issue_label or f"第 {dt.strftime('%Y%m%d')} 期"

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
  <div class="sheet">
    <div class="peel" title="回到顶部"></div>
    <span class="peel-tip">▴</span>
    <header class="masthead">
      <div class="corners"><span>{_esc(issue)}</span><span>AI 编纂 · 仅供阅读</span></div>
      <h1 class="title">{_esc(title)}</h1>
      <div class="subtitle">{_esc(masthead_en)}</div>
      <div class="dateline"><span>{_esc(_date_line(dt))}</span></div>
    </header>
    {weather_html}
    {lead_html}
    <div class="columns">
      {''.join(body_sections)}
    </div>
    <footer class="colophon">
      本报由 AI 助手自动编纂　·　{_esc(dt.strftime('%Y-%m-%d %H:%M'))}　·
      <a href="{_esc(archive_href)}">查看往期 →</a>
    </footer>
  </div>
</div>
<script>{_JS}</script>
</body>
</html>
"""


def render_archive(entries: list[tuple[str, str]], *, masthead_en: str = "ARCHIVE") -> str:
    """生成往期索引页。entries: [(date_str, href), ...]，按新到旧排列。"""
    items = "".join(
        f'<a class="article" href="{_esc(href)}"><span class="t">{_esc(d)} 早报</span>'
        f'<span class="src">{_esc(href)}</span></a>'
        for d, href in entries
    )
    if not items:
        items = '<section class="section"><h3>暂无往期</h3></section>'
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>早报 · 往期索引</title>
<style>{_CSS}</style>
</head>
<body>
<div class="stage">
  <div class="sheet">
    <header class="masthead">
      <h1 class="title">往期早报</h1>
      <div class="subtitle">{_esc(masthead_en)}</div>
    </header>
    <div class="columns">
      <section class="section"><h3>历史报纸</h3>{items}</section>
    </div>
    <footer class="colophon"><a href="index.html">← 返回今日</a></footer>
  </div>
</div>
</body>
</html>
"""


__all__ = ["render_paper", "render_archive"]
