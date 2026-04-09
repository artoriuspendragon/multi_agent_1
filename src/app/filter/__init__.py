"""
过滤模块（filter）。

对外入口：
- filter_and_sort(items, filter_config) -> List[RawItem]
"""

from __future__ import annotations

from app.config import FilterConfig
from app.models import RawItem

from .agent import filter_with_agent
from .rule import filter_rule_and_sort


def filter_and_sort(items: list[RawItem], filter_config: FilterConfig) -> list[RawItem]:
    """
    统一入口：根据 filter_config.strategy 执行规则与/或 Agent 过滤。
    """
    strategy = filter_config.strategy

    if strategy == "rule":
        return filter_rule_and_sort(items, filter_config)

    if strategy == "agent":
        # 纯 agent 模式，失败时按“宽松保留”降级
        try:
            return filter_with_agent(items, filter_config)
        except Exception:
            return items

    if strategy == "rule_then_agent":
        # 推荐策略：先规则粗筛，再把剩余交给 Agent 精筛。
        rule_result = filter_rule_and_sort(items, filter_config)
        try:
            return filter_with_agent(rule_result, filter_config)
        except Exception:
            # Agent 失败时回退 rule 结果
            return rule_result

    raise ValueError(f"unknown filter strategy: {strategy}")


__all__ = ["filter_and_sort"]

