"""
企业微信群机器人 Webhook 推送。

文档：https://developer.work.weixin.qq.com/document/path/91770
消息类型使用 text，单条最大 2048 字节。超长时自动截断。
"""

from __future__ import annotations

import httpx

from app.config import ChannelConfig
from app.models import Digest

from .base import _render_for_plain_text


class WecomSender:
    channel_type = "wecom"

    def send(
        self,
        digest: Digest,
        channel: ChannelConfig,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        if channel.type != "wecom":
            raise ValueError("WecomSender only supports channel.type='wecom'")
        if not channel.webhook_url:
            raise ValueError("wecom channel missing webhook_url")

        close_after = False
        if http_client is None:
            http_client = httpx.Client(timeout=httpx.Timeout(30))
            close_after = True

        try:
            content = _render_for_plain_text(digest).strip()

            # 企业微信 text 消息限制 2048 字节
            max_bytes = 2048
            encoded = content.encode("utf-8")
            if len(encoded) > max_bytes:
                content = encoded[: max_bytes - 9].decode("utf-8", errors="ignore") + "..."

            payload = {
                "msgtype": "text",
                "text": {"content": content},
            }

            resp = http_client.post(
                channel.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()

            data = resp.json()
            if data.get("errcode", 0) != 0:
                raise RuntimeError(
                    f"wecom webhook error: {data.get('errmsg', 'unknown')}"
                )
        finally:
            if close_after:
                http_client.close()
