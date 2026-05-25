"""
从结构化 Digest.sections 渲染邮件 HTML（内联样式，邮件客户端兼容）。

替代旧版“让 agent 直接产出 HTML”的做法：内容唯一来源是 sections，
邮件保持简洁（标题 + 链接），天气版面用卡片，Epic 免费游戏用图文卡片。
"""

from __future__ import annotations

import html
from urllib.parse import urlparse

from app.models import Digest, Section


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


def _is_weather(name: str) -> bool:
    return "天气" in name


def _is_epic(name: str) -> bool:
    return "Epic" in name or "epic" in name


def _weather_card(sec: Section) -> str:
    body = _esc(sec.text).replace("\n", "<br>")
    return (
        '<div style="background:#e3f2fd;border-radius:8px;padding:16px;margin:0 0 18px;">'
        f'<div style="font-size:16px;font-weight:bold;color:#0d47a1;margin-bottom:6px;">{_esc(sec.name)}</div>'
        f'<div style="font-size:14px;color:#37474f;line-height:1.7;">{body}</div></div>'
    )


def _epic_card(sec: Section) -> str:
    cards = ""
    for it in sec.items:
        extra = it.extra if isinstance(it.extra, dict) else {}
        cover = extra.get("cover") or ""
        free_end = extra.get("free_end") or ""
        price = extra.get("original_price_desc") or ""
        badge = "🎁 免费领取中" if extra.get("is_free_now") else "⏳ 即将免费"
        cards += (
            f'<a href="{_esc(it.link)}" target="_blank" style="text-decoration:none;color:inherit;display:block;">'
            '<div style="display:flex;border:1px solid #e0e0e0;border-radius:10px;overflow:hidden;margin-bottom:12px;background:#fff;">'
            + (f'<img src="{_esc(cover)}" style="width:120px;height:120px;object-fit:cover;display:block;flex-shrink:0;">' if cover else "")
            + '<div style="padding:12px 16px;">'
            f'<div style="font-size:16px;font-weight:bold;color:#212121;">{_esc(it.title)}'
            f'<span style="font-size:12px;color:#fff;background:#4caf50;border-radius:4px;padding:2px 8px;margin-left:8px;">{badge}</span></div>'
            f'<div style="font-size:13px;color:#9e9e9e;margin-top:6px;">截止：{_esc(free_end)}　<s>{_esc(price)}</s> <b style="color:#4caf50;">免费</b></div>'
            "</div></div></a>"
        )
    return (
        '<div style="margin-top:24px;padding-top:18px;border-top:2px solid #e0e0e0;">'
        f'<div style="font-size:20px;color:#212121;margin:0 0 14px;">{_esc(sec.name)}</div>{cards}</div>'
    )


def _news_section(sec: Section) -> str:
    rows = ""
    for it in sec.items:
        src = _domain(it.link)
        rows += (
            '<li style="margin:0 0 10px;">'
            f'<a href="{_esc(it.link)}" target="_blank" style="color:#1a73e8;text-decoration:none;font-size:15px;font-weight:600;">{_esc(it.title)}</a>'
            + (f'<span style="color:#9e9e9e;font-size:12px;"> · {_esc(src)}</span>' if src else "")
            + "</li>"
        )
    if not rows:
        return ""
    return (
        f'<h2 style="font-size:18px;color:#202124;border-bottom:2px solid #202124;padding-bottom:6px;margin:22px 0 12px;">{_esc(sec.name)}</h2>'
        f'<ul style="list-style:none;padding:0;margin:0;">{rows}</ul>'
    )


def render_email_html(digest: Digest) -> str:
    """从 sections 渲染简洁的邮件 HTML。"""
    title = digest.title or "每日早报"
    parts: list[str] = []
    epic_html = ""
    for sec in digest.sections:
        if _is_weather(sec.name) and sec.text:
            parts.append(_weather_card(sec))
        elif _is_epic(sec.name):
            epic_html = _epic_card(sec)  # 放最后
        else:
            parts.append(_news_section(sec))
    if epic_html:
        parts.append(epic_html)

    body = "".join(parts) or '<p style="color:#5f6368;">今日暂无内容。</p>'
    return (
        '<div style="max-width:680px;margin:0 auto;font-family:-apple-system,\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;color:#202124;padding:16px;">'
        f'<div style="text-align:center;border-bottom:3px double #202124;padding-bottom:12px;margin-bottom:16px;">'
        f'<div style="font-size:28px;font-weight:800;letter-spacing:.04em;">{_esc(title)}</div></div>'
        f'{body}'
        '<div style="text-align:center;color:#9aa0a6;font-size:12px;margin-top:24px;border-top:1px solid #dadce0;padding-top:10px;">由 AI 助手自动编纂</div>'
        "</div>"
    )


__all__ = ["render_email_html"]
