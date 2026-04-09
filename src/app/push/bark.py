"""
Bark 推送（iOS 自定义通知）。

PRD 参考：调用 Bark Server API：
- /{key}/{title}/{body}（title 可选）

实现使用 GET：
- URL 编码 title/body
- body 做长度截断，避免超出 URL/服务限制
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

import httpx

from app.config import ChannelConfig
from app.models import Digest

from .base import _render_for_plain_text


class BarkSender:
    channel_type = "bark"

    def send(
        self,
        digest: Digest,
        channel: ChannelConfig,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        if channel.type != "bark":
            raise ValueError("BarkSender only supports channel.type='bark'")
        if not channel.base_url or not channel.key:
            raise ValueError("bark channel missing base_url or key")

        if http_client is None:
            http_client = httpx.Client(timeout=httpx.Timeout(30))

        title = (digest.title or "").strip() or "Digest"
        body = _render_for_plain_text(digest).strip()

        # Bark 单条长度通常有限制；为安全起见做截断
        max_chars = 3800
        if len(body) > max_chars:
            body = body[: max_chars - 3] + "..."

        base = channel.base_url.rstrip("/")
        key = channel.key.strip()
        url = f"{base}/{quote(key)}/{quote(title)}/{quote(body)}"

        # Bark 返回一般为纯文本/简单状态码；只要 2xx 即视为成功
        resp = http_client.get(url)
        resp.raise_for_status()

