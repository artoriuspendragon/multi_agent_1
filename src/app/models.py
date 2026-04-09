"""
领域模型：RawItem、Digest、Section、RenderedDigest。

与 PRD 6.1、技术文档 6.1 对齐，供全管道（sources、dedup、filter、digest、push）使用。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, field_validator


def _parse_datetime(v: Optional[Union[datetime, str]]) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class RawItem(BaseModel):
    """
    从任意信息源解析得到的统一条目结构。
    id 可由 source_id + raw_id 生成，保证唯一。
    """

    id: str
    source_id: str
    raw_id: str
    title: str
    link: str
    summary: Optional[str] = None
    published_at: Optional[datetime] = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("published_at", mode="before")
    @classmethod
    def coerce_published_at(cls, v: Optional[Union[datetime, str]]) -> Optional[datetime]:
        return _parse_datetime(v)

    model_config = {"str_strip_whitespace": True, "extra": "allow"}


class Section(BaseModel):
    """早报中的一个分组，包含分组名与条目列表。"""

    name: str
    items: list[RawItem] = Field(default_factory=list)

    model_config = {"str_strip_whitespace": True}


class RenderedDigest(BaseModel):
    """早报按渠道需要的格式渲染后的字符串。"""

    text: Optional[str] = None
    markdown: Optional[str] = None
    html: Optional[str] = None

    model_config = {"str_strip_whitespace": True}


class Digest(BaseModel):
    """
    聚合后的早报对象。
    id 可为 uuid 或日期；generated_at 为 ISO8601 字符串。
    """

    id: str
    title: str
    generated_at: str
    sections: list[Section] = Field(default_factory=list)
    rendered: RenderedDigest = Field(default_factory=RenderedDigest)

    model_config = {"str_strip_whitespace": True}


# ---------- Agent 返回约定（供 filter/digest 模块解析用，不参与配置） ----------


class FilterAgentKeepIds(BaseModel):
    """过滤 Agent 返回方案 A：保留的条目 id 列表。"""

    keep_ids: list[str] = Field(default_factory=list)


class FilterAgentScoredItem(BaseModel):
    """过滤 Agent 返回方案 B：单条打分。"""

    id: str
    score: float


class FilterAgentScored(BaseModel):
    """过滤 Agent 返回方案 B：打分列表。"""

    scored: list[FilterAgentScoredItem] = Field(default_factory=list)
