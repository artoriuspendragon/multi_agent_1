"""
管道编排：sources → dedup → filter → digest → push。

与技术文档 5.1 对齐：run(config) -> PipelineResult。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from app.config import AppConfig
from app.dedup import deduplicate
from app.digest import generate_digest
from app.filter import filter_and_sort
from app.models import Digest, RawItem
from app.push import ChannelResult, send_all
from app.sources import fetch_all

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """一次管道运行的汇总结果，供 CLI/日志/可选 API 使用。"""

    steps_completed: list[str] = field(default_factory=list)
    raw_count: int = 0
    dedup_count: int = 0
    filtered_count: int = 0
    digest: Digest | None = None
    channel_results: list[ChannelResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """无致命错误（errors 为空）。"""
        return len(self.errors) == 0

    @property
    def push_success_count(self) -> int:
        return sum(1 for r in self.channel_results if r.success)


def run(
    config: AppConfig,
    *,
    timeout_per_source: int = 30,
    dedup_key: Literal["link", "raw_id"] = "link",
) -> PipelineResult:
    """
    执行完整管道。

    - 单步失败时尽量记录到 errors，不抛异常（便于 CLI 一次返回汇总）。
    - filter/digest 若因未实现的 Agent 策略失败，digest 可能为 None。
    """
    result = PipelineResult()

    # 1) 采集
    try:
        raw_items = fetch_all(config.sources, timeout_per_source=timeout_per_source)
        result.raw_count = len(raw_items)
        result.steps_completed.append("fetch")
        logger.info("pipeline fetch done raw_count=%d", result.raw_count)
    except Exception as e:
        msg = f"fetch failed: {e}"
        result.errors.append(msg)
        logger.exception("pipeline fetch failed")
        return result

    # 2) 去重
    try:
        deduped = deduplicate(raw_items, key=dedup_key)
        result.dedup_count = len(deduped)
        result.steps_completed.append("dedup")
        logger.info("pipeline dedup done dedup_count=%d", result.dedup_count)
    except Exception as e:
        msg = f"dedup failed: {e}"
        result.errors.append(msg)
        logger.exception("pipeline dedup failed")
        return result

    # 3) 过滤
    try:
        filtered = filter_and_sort(deduped, config.filter)
        result.filtered_count = len(filtered)
        result.steps_completed.append("filter")
        logger.info("pipeline filter done filtered_count=%d", result.filtered_count)

        # 按 source 统计过滤后的条目数
        source_counts: dict[str, int] = {}
        for item in filtered:
            source_counts[item.source_id] = source_counts.get(item.source_id, 0) + 1
        for sid, cnt in sorted(source_counts.items(), key=lambda x: -x[1]):
            logger.info("  source %-25s items=%d", sid, cnt)

    except Exception as e:
        msg = f"filter failed: {e}"
        result.errors.append(msg)
        logger.exception("pipeline filter failed")
        return result

    # 4) 天气（可选，不阻断 pipeline）
    weather_summary = None
    user_schedule = None
    if config.weather.enabled:
        try:
            from app.weather import fetch_weather
            weather_summary = fetch_weather(config.weather)
            user_schedule = config.weather.schedule
            result.steps_completed.append("weather")
            logger.info("pipeline weather done has_data=%s", weather_summary is not None)
        except Exception as e:
            logger.warning("pipeline weather failed: %s", e)

    # 5) 早报
    try:
        digest = generate_digest(
            filtered, config.digest,
            weather_summary=weather_summary,
            user_schedule=user_schedule,
        )
        result.digest = digest
        result.steps_completed.append("digest")
        logger.info("pipeline digest done title=%s", digest.title)
        logger.info("pipeline digest done content=%s", digest)

    except Exception as e:
        msg = f"digest failed: {e}"
        result.errors.append(msg)
        logger.exception("pipeline digest failed")
        return result

    # 5) 推送
    if not config.push.channels:
        result.steps_completed.append("push_skipped")
        logger.info("pipeline push skipped (no channels)")
        return result

    try:
        result.channel_results = send_all(result.digest, config.push)
        result.steps_completed.append("push")
        ok = result.push_success_count
        logger.info(
            "pipeline push done channels=%d success=%d",
            len(result.channel_results),
            ok,
        )
    except Exception as e:
        msg = f"push failed: {e}"
        result.errors.append(msg)
        logger.exception("pipeline push failed")

    return result


__all__ = ["run", "PipelineResult"]
