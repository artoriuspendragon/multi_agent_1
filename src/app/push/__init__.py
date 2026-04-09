"""
推送模块（push）对外入口。
"""

from __future__ import annotations

from app.config import PushConfig
from app.models import Digest

from .base import ChannelResult, send_all


__all__ = ["send_all", "ChannelResult", "PushConfig", "Digest"]

