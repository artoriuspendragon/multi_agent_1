"""
Agent 早报生成（MiniMax chatcompletion_v2）。

职责：
- 语义去重（不同源报道同一事件只保留一条）
- 按报纸版面分类（头条、AI/技术、国际、财经、游戏、八卦、其他）
- 按用户兴趣排优先级
- 英文标题翻译为中文
- 输出结构化 JSON + 报纸风格 HTML
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.agent import call_minimax_chat, extract_json_object
from app.config import DigestConfig
from app.models import Digest, RawItem, RenderedDigest, Section

logger = logging.getLogger(__name__)

# ---------- Prompt 模板 ----------

_SYSTEM_PROMPT = """\
你是一位资深报纸主编，负责每日新闻早报的编排。你需要从一批新闻标题中完成以下工作：

## 工作流程

### 第一步：去重
- 不同来源报道同一事件的，只保留信息最丰富的一条
- 高度相似的标题视为同一新闻

### 第二步：分类
将新闻分到以下版面（section），每个版面 5-10 条，头条最多 5 条：

1. **🌤️ 今日天气** —— 如果输入中包含天气数据，放在最前面。根据用户作息给出穿衣和出行建议
2. **📰 今日头条** —— 当天最重大的新闻（能让世界"震惊"的事件：重大国际政治变化、某领域技术重大突破、重要人物伤亡等）。如果当天没有足够震撼的新闻，可以少于 5 条，不要凑数
3. **🤖 AI与技术** —— AI、编程、软件工程、技术产品等
4. **🌍 国际新闻** —— 国际政治、外交、军事、社会
5. **💰 财经** —— 经济、金融、商业、创业
6. **🎮 游戏** —— 游戏行业、新游戏、电竞
7. **🍵 八卦茶余** —— 娱乐、明星、趣闻（可选：没有就不输出这个版面）
8. **📋 其他** —— 不属于以上分类的新闻

### 天气版面特殊要求
如果输入中包含天气数据和用户作息信息，请生成以下内容（不是新闻列表，而是一段文字）：
- 一句话总结今天天气
- 按用户作息的关键时段（出门、午餐、下班）给出具体建议：
  - 穿什么衣服合适（根据温度、体感温度、风力）
  - 要不要带伞（根据降水概率）
  - 空气质量是否需要戴口罩
- 语气亲切自然，像朋友提醒一样，不要像天气预报播报

### 第三步：翻译
- 英文标题必须翻译为中文（保留原文链接）
- 如果输入里有 description 字段，也翻译成中文并尽量精炼
- 翻译要自然流畅，不要机翻味

### 第四步：输出
严格按照下方 JSON 格式输出，不要输出任何解释文字。

## 用户兴趣偏好（影响排序优先级）
最关注：AI、Java 技术类 > 国际新闻 > 游戏 > 其他

## 输出 JSON 格式
```json
{
  "title": "每日早报 YYYY-MM-DD",
  "sections": [
    {
      "name": "🌤️ 今日天气",
      "text": "天气概况和建议的纯文本（不是items数组）"
    },
    {
      "name": "📰 今日头条",
      "items": [
        {"title": "中文标题", "link": "原始链接"}
      ]
    },
    {
      "name": "🤖 AI与技术",
      "items": [...]
    }
  ],
  "rendered": {
    "html": "完整的 HTML 报纸页面（见下方模板）"
  }
}
```
注意：天气版面用 "text" 字段（字符串），其他新闻版面用 "items" 字段（数组）。

## HTML 模板要求
rendered.html 必须是一个完整的、可直接在邮件中显示的 HTML 页面，要求：
- 使用内联样式（邮件客户端不支持 <style> 标签）
- 整体宽度 max-width: 680px，居中
- 报头：大标题 + 日期，有底部边框分隔
- 天气版面：用浅蓝色背景卡片样式（background: #e3f2fd; border-radius: 8px; padding: 16px），图标用 emoji，文字分段落展示建议
- 每个新闻版面：版面名作为小标题（带 emoji），下面是新闻列表
- 每条新闻：标题可点击（a 标签链接到原文），颜色 #1a73e8
- 头条版面用稍大字号或加粗突出
- 版面之间有分隔线
- 整体风格简洁大方，配色以深灰文字 + 白色背景 + 蓝色链接为主
- 底部加一行小字："由 AI 助手自动生成"
"""


def _build_items_payload(
    items: list[RawItem],
    max_n: int,
    *,
    include_summary: bool = False,
    max_summary_chars: int = 200,
) -> list[dict[str, str]]:
    """默认只提取 title + link + source_id，按需附带 summary。"""
    subset = items[:max_n]
    payload: list[dict[str, str]] = []
    for it in subset:
        row: dict[str, str] = {
            "source": it.source_id,
            "title": it.title,
            "link": it.link,
        }
        if include_summary:
            row["description"] = (it.summary or "")[:max_summary_chars]
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
    parts.append("\n请按照系统指令完成天气建议、去重、分类、翻译，并输出 JSON。")

    return "\n".join(parts)


def _section_limit(name: str) -> int:
    if "头条" in name:
        return 5
    return 10


def _build_epic_freegame_html(epic_items: list[RawItem]) -> str:
    """为 Epic 免费游戏构建底部 HTML 卡片区域。"""
    if not epic_items:
        return ""

    cards_html = ""
    for item in epic_items:
        extra = item.extra if isinstance(item.extra, dict) else {}
        title = item.title or "Unknown Game"
        link = item.link or "#"
        cover = extra.get("cover") or ""
        free_end = extra.get("free_end") or ""
        original_price_desc = extra.get("original_price_desc") or ""
        is_free_now = extra.get("is_free_now", False)
        description = (item.summary or "")[:120]
        if description and len(item.summary or "") > 120:
            description += "..."

        # 状态标签
        if is_free_now:
            badge = (
                '<span style="display:inline-block;background:#4caf50;color:#fff;'
                'font-size:12px;padding:2px 8px;border-radius:4px;margin-left:8px;">'
                '🎁 免费领取中</span>'
            )
            expire_text = f'⏰ 截止：{free_end}' if free_end else ''
        else:
            free_start = extra.get("free_start") or ""
            badge = (
                '<span style="display:inline-block;background:#ff9800;color:#fff;'
                'font-size:12px;padding:2px 8px;border-radius:4px;margin-left:8px;">'
                '⏳ 即将免费</span>'
            )
            expire_text = f'🕐 免费时间：{free_start} ~ {free_end}' if free_start else ''

        cards_html += f'''
        <a href="{link}" target="_blank" style="text-decoration:none;color:inherit;display:block;">
          <div style="display:flex;border:1px solid #e0e0e0;border-radius:10px;overflow:hidden;
                      margin-bottom:12px;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
            <div style="flex-shrink:0;width:140px;height:140px;overflow:hidden;">
              <img src="{cover}" alt="{title}"
                   style="width:140px;height:140px;object-fit:cover;display:block;" />
            </div>
            <div style="padding:12px 16px;flex:1;min-width:0;">
              <div style="font-size:16px;font-weight:bold;color:#212121;margin-bottom:6px;">
                {title}{badge}
              </div>
              <div style="font-size:13px;color:#757575;margin-bottom:6px;
                          overflow:hidden;text-overflow:ellipsis;
                          display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;">
                {description}
              </div>
              <div style="font-size:13px;color:#9e9e9e;margin-bottom:4px;">
                {expire_text}
              </div>
              <div style="font-size:13px;">
                <span style="text-decoration:line-through;color:#9e9e9e;">{original_price_desc}</span>
                <span style="color:#4caf50;font-weight:bold;margin-left:6px;">免费</span>
              </div>
            </div>
          </div>
        </a>'''

    return f'''
    <div style="margin-top:24px;padding-top:20px;border-top:2px solid #e0e0e0;">
      <h2 style="font-size:20px;color:#212121;margin:0 0 16px 0;">
        🎮 Epic 免费游戏
      </h2>
      {cards_html}
      <div style="text-align:center;margin-top:8px;">
        <a href="https://store.epicgames.com/zh-CN/free-games"
           target="_blank"
           style="font-size:13px;color:#1a73e8;text-decoration:none;">
          查看 Epic 商店更多免费游戏 →
        </a>
      </div>
    </div>'''


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

    # 分离 Epic 免费游戏条目，单独渲染，不发给 AI
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
        system_name=_SYSTEM_PROMPT,
        user_name="早报编辑",
        user_content=user_content,
        timeout_seconds=cfg.timeout_seconds,
    )

    logger.debug("digest agent raw response: %s", text[:2000])

    # 解析结构化 JSON
    data = extract_json_object(text)
    title = str(data.get("title") or title_default)

    # 解析 sections
    sections_data = data.get("sections") if isinstance(data.get("sections"), list) else []
    sections: list[Section] = []
    for s in sections_data:
        if not isinstance(s, dict):
            continue
        s_name = str(s.get("name") or "Section")
        section_cap = _section_limit(s_name)
        s_items: list[RawItem] = []
        rows = s.get("items", []) if isinstance(s.get("items"), list) else []
        for row in rows[:section_cap]:
            if not isinstance(row, dict):
                continue
            link = str(row.get("link") or "")
            title_i = str(row.get("title") or link or "Untitled")
            raw_id = link or title_i
            s_items.append(
                RawItem(
                    id=f"agent:{raw_id}",
                    source_id="agent",
                    raw_id=raw_id,
                    title=title_i,
                    link=link,
                    summary=None,
                    published_at=None,
                    extra={},
                )
            )
        # 文字版面（如天气）：用 text 字段，没有 items 也保留
        s_text = s.get("text")
        s_text = str(s_text).strip() if isinstance(s_text, str) and s_text.strip() else None
        if s_items or s_text:
            sections.append(Section(name=s_name, items=s_items, text=s_text))

    # 解析 rendered
    rendered_data = data.get("rendered") if isinstance(data.get("rendered"), dict) else {}
    html_content = rendered_data.get("html") or None
    markdown_content = rendered_data.get("markdown") or None

    # 如果 AI 没返回 markdown，从 sections 生成一份作为纯文本 fallback
    if not markdown_content:
        md_lines = [f"# {title}", ""]
        for sec in sections:
            md_lines.append(f"## {sec.name}")
            for it in sec.items:
                md_lines.append(f"- [{it.title}]({it.link})" if it.link else f"- {it.title}")
            md_lines.append("")
        markdown_content = "\n".join(md_lines)

    # 将 Epic 免费游戏卡片追加到 HTML 底部（在 "AI 助手自动生成" 之前）
    epic_html_block = _build_epic_freegame_html(epic_items)
    if epic_html_block and html_content:
        # 尝试插入到 footer 提示语之前，若找不到则直接追加
        footer_marker = "由 AI 助手自动生成"
        if footer_marker in html_content:
            # 在 footer 所在的 div/p 之前插入
            import re as _re
            # 匹配包含 footer 文字的标签
            pattern = _re.compile(
                r'(<(?:div|p|span)[^>]*>[^<]*' + _re.escape(footer_marker) + r')',
                _re.IGNORECASE,
            )
            match = pattern.search(html_content)
            if match:
                insert_pos = match.start()
                html_content = html_content[:insert_pos] + epic_html_block + "\n" + html_content[insert_pos:]
            else:
                # footer 存在但格式未匹配，在 </body> 或末尾插入
                for tag in ("</body>", "</div></div>"):
                    rpos = html_content.rfind(tag)
                    if rpos != -1:
                        html_content = html_content[:rpos] + epic_html_block + "\n" + html_content[rpos:]
                        break
                else:
                    html_content += epic_html_block
        else:
            # 没有 footer：在 </body> 前或末尾插入
            rpos = html_content.rfind("</body>")
            if rpos != -1:
                html_content = html_content[:rpos] + epic_html_block + "\n" + html_content[rpos:]
            else:
                html_content += epic_html_block

    elif epic_html_block and not html_content:
        html_content = epic_html_block

    # Epic 游戏也追加到 markdown
    if epic_items:
        md_lines_epic = ["\n## 🎮 Epic 免费游戏"]
        for it in epic_items:
            extra = it.extra if isinstance(it.extra, dict) else {}
            free_end = extra.get("free_end") or ""
            price = extra.get("original_price_desc") or ""
            status = "🎁 免费中" if extra.get("is_free_now") else "⏳ 即将免费"
            md_lines_epic.append(
                f"- [{it.title}]({it.link}) | {status} | ~~{price}~~ | 截止 {free_end}"
            )
        markdown_content += "\n".join(md_lines_epic)

    rendered = RenderedDigest(
        html=html_content,
        markdown=markdown_content,
        text=markdown_content,
    )

    logger.info(
        "digest agent: parsed %d sections, html=%s",
        len(sections),
        "yes" if html_content else "no",
    )

    return Digest(
        id=title,
        title=title,
        generated_at=now.isoformat(),
        sections=sections,
        rendered=rendered,
    )
