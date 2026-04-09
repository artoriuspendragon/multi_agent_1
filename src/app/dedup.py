"""
去重模块（Dedup）。

PRD 约定（F6）：
- 同一篇文章在多源出现时去重
- 归一化维度：`link` 或 `raw_id`

实现约定：
- 稳定去重：保留首次出现的条目，去掉后续重复
- `link` 去重会做基础归一化：trim + 移除尾部 '/' + 去除 fragment '#...'
"""

from __future__ import annotations

from typing import Literal

from app.models import RawItem


def normalize_link_for_dedup(link: str) -> str:
    """
    对 link 做轻量归一化以减少“同一链接不同写法”的重复。
    说明：避免过度规范化（如大小写域名、排序 query 等），以免误伤。
    """
    s = link.strip()
    if "#" in s:
        s = s.split("#", 1)[0]
    # 移除尾部 '/'，避免 https://x/a 与 https://x/a/ 被认为不同
    while s.endswith("/"):
        s = s[:-1]
    return s


def _dedup_key(item: RawItem, key: Literal["link", "raw_id"]) -> str:
    if key == "raw_id":
        return str(item.raw_id)
    # key == "link"
    return normalize_link_for_dedup(item.link)


def deduplicate(
    items: list[RawItem],
    key: Literal["link", "raw_id"] = "link",
) -> list[RawItem]:
    """
    稳定去重：保留首次出现的 RawItem。
    """
    if not items:
        return []

    seen: set[str] = set()
    out: list[RawItem] = []

    for item in items:
        # link 可能为空（某些 crawler/API 宽松映射时）；如为空则退化为 raw_id 去重
        if key == "link" and not item.link:
            dedup_key = str(item.raw_id)
        else:
            dedup_key = _dedup_key(item, key=key)

        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        out.append(item)

    return out

