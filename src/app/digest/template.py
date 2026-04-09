"""
模板早报生成（digest.strategy='template'）。

不强依赖第三方模板引擎：title_template 只对 {{date}} 做替换，
正文通过固定的 markdown 结构生成。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import DigestConfig
from app.models import Digest, RenderedDigest, RawItem, Section


def _render_title(title_template: str, date: datetime) -> str:
    # 简化实现：仅替换 PRD 中明确使用的 {{date}}
    # 兼容常见格式：YYYY-MM-DD
    date_str = date.date().isoformat()
    return title_template.replace("{{date}}", date_str).replace("{{date_iso}}", date_str)


def _group_items(items: list[RawItem], group_by: str) -> list[Section]:
    if group_by == "none":
        return [Section(name="All", items=items)]

    if group_by == "source":
        sections: dict[str, list[RawItem]] = {}
        for it in items:
            sections.setdefault(it.source_id, []).append(it)
        # 保持稳定：按首次出现的 source_id 顺序
        ordered_keys: list[str] = []
        seen = set()
        for it in items:
            if it.source_id not in seen:
                ordered_keys.append(it.source_id)
                seen.add(it.source_id)
        return [Section(name=k, items=sections[k]) for k in ordered_keys]

    # group_by == "tag"
    # RawItem.extra 是宽松的 dict：优先读取 extra['tags'] 或 extra['tag']
    sections: dict[str, list[RawItem]] = {}
    ordered_keys: list[str] = []
    seen = set()
    for it in items:
        tags: list[str] = []
        if isinstance(it.extra, dict):
            v = it.extra.get("tags") or it.extra.get("tag")
            if isinstance(v, list):
                tags = [str(x).strip() for x in v if str(x).strip()]
            elif isinstance(v, str):
                # 允许用逗号分隔
                parts = [p.strip() for p in v.split(",")]
                tags = [p for p in parts if p]
        if not tags:
            tags = ["untagged"]
        for tag in tags:
            sections.setdefault(tag, []).append(it)
            if tag not in seen:
                ordered_keys.append(tag)
                seen.add(tag)
    return [Section(name=k, items=sections.get(k, [])) for k in ordered_keys]


def _render_markdown(digest_title: str, sections: list[Section]) -> str:
    # Markdown 早报结构（稳定、易读、适配 Telegram/邮件等）
    # - 置顶标题
    # - 分组标题
    # - 条目：- [title](link) + summary（可选）
    lines: list[str] = []
    lines.append(f"# {digest_title}")
    lines.append("")

    if not sections or all(len(s.items) == 0 for s in sections):
        lines.append("没有匹配的新内容。")
        return "\n".join(lines).strip()

    for sec in sections:
        if not sec.items:
            continue
        lines.append(f"## {sec.name}")
        for it in sec.items:
            title = (it.title or "").strip() or it.link
            link = it.link
            bullet = f"- [{title}]({link})" if link else f"- {title}"
            lines.append(bullet)
            if it.summary:
                # summary 太长会影响推送长度：这里不做强截断，交由 push 层处理
                for sm_line in str(it.summary).strip().splitlines():
                    lines.append(f"  - {sm_line}")
        lines.append("")

    return "\n".join(lines).rstrip()


def generate_digest_template(items: list[RawItem], digest_config: DigestConfig) -> Digest:
    now = datetime.now(timezone.utc)
    digest_title = _render_title(digest_config.title_template, now)

    max_items = digest_config.max_items
    if max_items is not None and max_items > 0:
        items = items[:max_items]

    sections = _group_items(items, digest_config.group_by)

    rendered_markdown = _render_markdown(digest_title, sections)

    # Digest.rendered 同时可填 markdown/text/html；这里先给 markdown
    rendered = RenderedDigest(markdown=rendered_markdown, text=rendered_markdown)

    return Digest(
        id=digest_title,  # 简化：可用 uuid/date；先满足结构即可
        title=digest_title,
        generated_at=now.isoformat(),
        sections=sections,
        rendered=rendered,
    )

