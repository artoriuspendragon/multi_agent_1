"""
sources 基础能力：Fetcher 抽象、通用 URL/时间解析工具、异常类型。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from typing import Any, Protocol
from urllib.parse import urljoin

import httpx

from app.config import SourceConfig
from app.models import RawItem


class FetcherError(Exception):
    """信息源拉取/解析失败的统一异常类型。"""


class BaseFetcher(Protocol):
    def fetch(self, source: SourceConfig, client: httpx.Client) -> list[RawItem]:
        """拉取并解析单个 source，返回 RawItem 列表。"""


def normalize_url(base_url: str | None, url: str | None) -> str | None:
    if not url:
        return None
    if base_url:
        return urljoin(base_url, url)
    return url


def parse_datetime(v: Any) -> datetime | None:
    """
    将常见的 RSS/API 日期格式解析为 datetime。

    - 支持 datetime / ISO8601 / RFC822（email.utils.parsedate_to_datetime）
    """
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, (int, float)):
        # 可能是 unix timestamp（秒）
        try:
            return datetime.fromtimestamp(v)
        except Exception:
            return None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        # 兼容 ISO8601 结尾 Z
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            pass
        try:
            return parsedate_to_datetime(s)
        except Exception:
            return None
    return None


def make_item_ids(source_id: str, raw_id: str | None, link: str | None) -> tuple[str, str]:
    """
    生成 RawItem 的 id 与 raw_id。

    - raw_id：优先使用传入的 raw_id；否则使用 link 的哈希。
    - id：source_id + raw_id 的组合（用于去重/追踪）。
    """
    if not raw_id:
        if link:
            raw_id = sha256(link.encode("utf-8")).hexdigest()[:16]
        else:
            raw_id = sha256(f"{source_id}:{datetime.utcnow().isoformat()}".encode("utf-8")).hexdigest()[:16]
    item_id = f"{source_id}:{raw_id}"
    return item_id, raw_id

