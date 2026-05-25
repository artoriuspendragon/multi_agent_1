"""
推送模块（push）的基础协议与聚合入口。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import ChannelConfig, PushConfig
from app.models import Digest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChannelResult:
    channel_type: str
    success: bool
    error: str | None = None


class Sender(Protocol):
    channel_type: str

    def send(
        self,
        digest: Digest,
        channel: ChannelConfig,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        """发送单个 Digest 到单个渠道。失败时抛异常。"""


def _render_for_plain_text(digest: Digest) -> str:
    if digest.rendered.text:
        return digest.rendered.text
    if digest.rendered.markdown:
        # 最简单：把 markdown 链接语法保留原样，或直接用 markdown 文本
        return digest.rendered.markdown
    if digest.sections:
        return digest.title
    return digest.title


def send_all(digest: Digest, push_config: PushConfig) -> list[ChannelResult]:
    """
    依次发送到所有 enabled 的渠道；单渠道失败不影响其他渠道。
    """
    if not push_config.channels:
        return []

    from .email import EmailSender
    from .bark import BarkSender
    from .msgraph import MsGraphSender
    from .wecom import WecomSender
    from .webpaper import WebPaperSender

    # 复用 http client（仅 bark/telegram 等用得到）
    http_client: httpx.Client | None = None
    try:
        http_client = httpx.Client(timeout=httpx.Timeout(30))
        senders: dict[str, Sender] = {
            "email": EmailSender(),
            "bark": BarkSender(),
            "msgraph": MsGraphSender(),
            "wecom": WecomSender(),
            "webpaper": WebPaperSender(),
        }

        results: list[ChannelResult] = []
        for ch in push_config.channels:
            if not ch.enabled:
                continue

            # dry_run 模式：跳过实际发送，仅记录日志
            if push_config.dry_run:
                logger.info(
                    "[push] dry_run=true, skipping real send for channel=%s to=%s",
                    ch.type,
                    getattr(ch, "to", None) or getattr(ch, "webhook_url", None) or getattr(ch, "output_dir", None) or "N/A",
                )
                results.append(ChannelResult(channel_type=ch.type, success=True, error="dry_run"))
                continue

            sender = senders.get(ch.type)
            if not sender:
                results.append(
                    ChannelResult(channel_type=ch.type, success=False, error=f"unsupported channel type: {ch.type}")
                )
                continue
            try:
                sender.send(digest, ch, http_client=http_client)
                results.append(ChannelResult(channel_type=ch.type, success=True))
            except Exception as e:
                results.append(ChannelResult(channel_type=ch.type, success=False, error=str(e)))
        return results
    finally:
        if http_client is not None:
            http_client.close()


__all__ = ["send_all", "ChannelResult"]

