"""
私人消息流推送助手 - 主包。

对外暴露：
- models: RawItem, Digest, Section, RenderedDigest 等
- config: load_config, AppConfig 等
"""

from app.config import load_config, AppConfig
from app.models import Digest, RawItem, RenderedDigest, Section
from app.sources import fetch_all
from app.dedup import deduplicate
from app.filter import filter_and_sort
from app.digest import generate_digest
from app.push import send_all, ChannelResult
from app.pipeline import run, PipelineResult

__all__ = [
    "load_config",
    "AppConfig",
    "Digest",
    "RawItem",
    "RenderedDigest",
    "Section",
    "fetch_all",
    "deduplicate",
    "filter_and_sort",
    "generate_digest",
    "send_all",
    "ChannelResult",
    "run",
    "PipelineResult",
]
