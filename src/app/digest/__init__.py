"""
早报生成模块（digest）。

对外入口：
- generate_digest(items, digest_config, ...) -> Digest
"""

from __future__ import annotations

from app.config import DigestConfig
from app.models import Digest, RawItem

from .agent import generate_with_agent
from .template import generate_digest_template


def generate_digest(
    items: list[RawItem],
    digest_config: DigestConfig,
    *,
    weather_summary: str | None = None,
    user_schedule: str | None = None,
) -> Digest:
    strategy = digest_config.strategy

    if strategy == "template":
        return generate_digest_template(items, digest_config)

    if strategy == "agent":
        # 纯 agent 失败时回退 template
        try:
            return generate_with_agent(
                items, digest_config,
                weather_summary=weather_summary,
                user_schedule=user_schedule,
            )
        except Exception:
            return generate_digest_template(items, digest_config)

    if strategy == "template_then_agent":
        draft = generate_digest_template(items, digest_config)
        try:
            return generate_with_agent(
                items, digest_config,
                weather_summary=weather_summary,
                user_schedule=user_schedule,
            )
        except Exception:
            return draft

    raise ValueError(f"unknown digest strategy: {strategy}")


__all__ = ["generate_digest"]
