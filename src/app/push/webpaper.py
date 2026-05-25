"""
webpaper 渠道：把 Digest 渲染为拟物报纸网页并写入站点目录（默认 docs/），
可选自动 git 提交推送，供 GitHub Pages 展示。
"""

from __future__ import annotations

import logging

import httpx

from app.config import ChannelConfig
from app.models import Digest
from app.web.publish import publish_paper

logger = logging.getLogger(__name__)


class WebPaperSender:
    channel_type = "webpaper"

    def send(
        self,
        digest: Digest,
        channel: ChannelConfig,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        if channel.type != "webpaper":
            raise ValueError("WebPaperSender only supports channel.type='webpaper'")

        result = publish_paper(
            digest,
            output_dir=channel.output_dir,
            git_publish=channel.git_publish,
            git_branch=channel.git_branch,
            masthead_en=channel.masthead_en,
        )
        logger.info(
            "[webpaper] wrote %s (index=%s, archive=%s)",
            result.page_path, result.index_path, result.archive_path,
        )

        # 请求发布但既没推送也不是“无变化”，视为失败
        if channel.git_publish and not result.git_pushed:
            msg = result.git_message or "unknown"
            if msg != "no changes to publish":
                raise RuntimeError(f"webpaper git publish failed: {msg}")
