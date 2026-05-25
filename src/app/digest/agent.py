"""
Agent 早报生成（MiniMax chatcompletion_v2）。

职责：
- 语义去重（不同源报道同一事件只保留一条）
- 按可配置的报纸版面分类（头条 + 多个类目）
- 为每条新闻撰写中文摘要（newspaper 模式）
- 按用户兴趣排优先级
- 英文标题/摘要翻译为中文
- 仅输出结构化 JSON；邮件与网页 HTML 均由 Python 从 sections 渲染
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.agent import call_minimax_chat, extract_json_object
from app.config import DigestConfig, DigestAgentConfig
from app.models import Digest, RawItem, RenderedDigest, Section

from .render import render_email_html

logger = logging.getLogger(__name__)


# ---------- Prompt 构建 ----------


def _build_system_prompt(cfg: DigestAgentConfig) -> str:
    """根据配置（版面、条数、摘要）动态拼装系统提示词。"""
    cat_lines = []
    for name in cfg.sections:
        if "头条" in name:
            cap = cfg.headline_count
            note = "当天最重大、最具影响力的新闻；不足也不要凑数"
        else:
            cap = cfg.items_per_section
            note = "该类目下值得一读的新闻"
        cat_lines.append(f"- **{name}**（最多 {cap} 条）：{note}")
    categories = "\n".join(cat_lines)

    if cfg.include_item_summary:
        summary_rule = (
            f"\n### 撰写摘要\n"
            f"- 为**每一条**新闻写一段中文摘要，约 {cfg.summary_target_chars} 字（2-3 句）\n"
            f"- 客观概括新闻核心：发生了什么、关键数据/人物、为何重要；不要标题党、不要营销腔\n"
            f"- 英文内容先理解再用通顺中文转述\n"
            f'- 摘要写入每条的 "summary" 字段\n'
        )
        summary_field = '"summary": "2-3句中文摘要", '
    else:
        summary_rule = ""
        summary_field = ""

    return f"""\
你是一位资深报纸主编，负责每日新闻早报的编排。请从一批新闻条目中完成以下工作：

### 第一步：去重
- 不同来源报道同一事件的，只保留信息最丰富的一条；高度相似的标题视为同一新闻

### 第二步：分类（报纸版面）
将新闻分到以下版面（section），尽量填满各版面但只收录有价值的内容：

{categories}

另外：
- 🌤️ 今日天气：如输入包含天气数据，作为**第一个** section，用 "text" 字段给出穿衣/出行建议（亲切自然，按用户作息分时段），不是新闻列表
- 一条新闻只归入最合适的一个版面；空版面可省略
{summary_rule}
### 第三步：翻译
- 英文标题必须翻译为通顺中文（保留原始链接）

### 第四步：输出
严格输出**一个 JSON 对象**，不要输出任何解释文字或代码块标记。

## 输出 JSON 格式
{{
  "title": "每日早报 YYYY-MM-DD",
  "sections": [
    {{"name": "🌤️ 今日天气", "text": "天气概况与建议（字符串）"}},
    {{"name": "📰 今日头条", "items": [
      {{"title": "中文标题", "link": "原始链接", {summary_field}"source": "来源名(可选)"}}
    ]}}
  ]
}}
注意：天气版面用 "text"（字符串），新闻版面用 "items"（数组）。务必输出合法 JSON。
"""


def _build_items_payload(
    items: list[RawItem],
    max_n: int,
    *,
    include_summary: bool = False,
    max_summary_chars: int = 200,
) -> list[dict[str, str]]:
    """提取 title + link + source，按需附带 summary（供 agent 撰写摘要参考）。"""
    subset = items[:max_n]
    payload: list[dict[str, str]] = []
    for it in subset:
        row: dict[str, str] = {"source": it.source_id, "title": it.title, "link": it.link}
        if include_summary and it.summary:
            row["description"] = it.summary[:max_summary_chars]
        payload.append(row)
    return payload


def _render_user_prompt(
    *,
    date_str: str,
    items_payload: list[dict[str, str]],
    constraints: str,
    prompt_template: str | None,
    weather_summary: str | None = None,
    user_schedule: str | None = None,
) -> str:
    items_json = json.dumps(items_payload, ensure_ascii=False, separators=(",", ":"))
    if prompt_template:
        return (
            prompt_template.replace("{date}", date_str)
            .replace("{items_json}", items_json)
            .replace("{constraints}", constraints)
        )

    parts = [f"今天日期：{date_str}"]
    if weather_summary:
        parts.append(f"\n## 今日天气数据\n{weather_summary}")
    if user_schedule:
        parts.append(f"\n## 用户作息\n{user_schedule}")
    parts.append(f"\n## 新闻条目（JSON）\n{items_json}")
    parts.append(f"\n额外约束：{constraints}")
    parts.append("\n请按系统指令完成去重、分类、摘要、翻译，并仅输出 JSON。")
    return "\n".join(parts)


def _section_cap(name: str, cfg: DigestAgentConfig) -> int:
    return cfg.headline_count if "头条" in name else cfg.items_per_section


def generate_with_agent(
    items: list[RawItem],
    digest_config: DigestConfig,
    *,
    weather_summary: str | None = None,
    user_schedule: str | None = None,
) -> Digest:
    if not digest_config.agent:
        raise ValueError("digest.agent is required for agent generation")

    cfg = digest_config.agent
    now = datetime.now(timezone.utc)
    date_str = now.date().isoformat()
    title_default = digest_config.title_template.replace("{{date}}", date_str)

    # Epic 免费游戏单独处理，不发给 agent
    epic_items = [it for it in items if it.source_id == "epic-freegame"]
    non_epic_items = [it for it in items if it.source_id != "epic-freegame"]

    max_n = max(1, min(cfg.max_input_items, len(non_epic_items) if non_epic_items else 1))
    items_payload = _build_items_payload(
        non_epic_items,
        max_n,
        include_summary=cfg.include_summary,
        max_summary_chars=cfg.max_summary_chars,
    )
    user_content = _render_user_prompt(
        date_str=date_str,
        items_payload=items_payload,
        constraints=cfg.constraints,
        prompt_template=cfg.prompt_template,
        weather_summary=weather_summary,
        user_schedule=user_schedule,
    )

    logger.info("digest agent: sending %d items to MiniMax", len(items_payload))

    text = call_minimax_chat(
        endpoint=cfg.endpoint,
        api_key=cfg.api_key,
        model=cfg.model,
        system_name=_build_system_prompt(cfg),
        user_name="早报编辑",
        user_content=user_content,
        timeout_seconds=cfg.timeout_seconds,
    )
    logger.debug("digest agent raw response: %s", text[:2000])

    data = extract_json_object(text)
    title = str(data.get("title") or title_default)

    sections_data = data.get("sections") if isinstance(data.get("sections"), list) else []
    sections: list[Section] = []
    for s in sections_data:
        if not isinstance(s, dict):
            continue
        s_name = str(s.get("name") or "Section")
        cap = _section_cap(s_name, cfg)
        s_items: list[RawItem] = []
        rows = s.get("items", []) if isinstance(s.get("items"), list) else []
        for row in rows[:cap]:
            if not isinstance(row, dict):
                continue
            link = str(row.get("link") or "")
            title_i = str(row.get("title") or link or "Untitled")
            summary_i = row.get("summary")
            summary_i = str(summary_i).strip() if isinstance(summary_i, str) and summary_i.strip() else None
            raw_id = link or title_i
            extra: dict = {}
            if row.get("source"):
                extra["source_name"] = str(row.get("source"))
            if row.get("time"):
                extra["time"] = str(row.get("time"))
            s_items.append(
                RawItem(
                    id=f"agent:{raw_id}",
                    source_id="agent",
                    raw_id=raw_id,
                    title=title_i,
                    link=link,
                    summary=summary_i,
                    published_at=None,
                    extra=extra,
                )
            )
        s_text = s.get("text")
        s_text = str(s_text).strip() if isinstance(s_text, str) and s_text.strip() else None
        if s_items or s_text:
            sections.append(Section(name=s_name, items=s_items, text=s_text))

    # 追加 Epic 免费游戏版面（保留封面/价格等 extra）
    if epic_items:
        sections.append(Section(name="🎁 Epic 免费游戏", items=epic_items))

    # 纯文本 / markdown fallback（含摘要）
    md_lines = [f"# {title}", ""]
    for sec in sections:
        md_lines.append(f"## {sec.name}")
        if sec.text:
            md_lines.append(sec.text)
        for it in sec.items:
            md_lines.append(f"- [{it.title}]({it.link})" if it.link else f"- {it.title}")
            if it.summary:
                md_lines.append(f"  - {it.summary}")
        md_lines.append("")
    markdown_content = "\n".join(md_lines)

    digest = Digest(
        id=title,
        title=title,
        generated_at=now.isoformat(),
        sections=sections,
        rendered=RenderedDigest(markdown=markdown_content, text=markdown_content),
    )
    # 邮件 HTML 由 Python 从 sections 渲染（简洁版）
    digest.rendered = RenderedDigest(
        html=render_email_html(digest),
        markdown=markdown_content,
        text=markdown_content,
    )

    logger.info(
        "digest agent: parsed %d sections, %d items",
        len(sections),
        sum(len(s.items) for s in sections),
    )
    return digest
