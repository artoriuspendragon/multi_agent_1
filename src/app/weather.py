"""
天气数据获取模块。

调用外部天气 API，返回结构化天气摘要（供 digest agent 使用）。
只提取关键时段信息，减少传给大模型的 token。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import WeatherConfig

logger = logging.getLogger(__name__)

# 用户作息关键时段（小时）
_KEY_HOURS = {
    10: "出门上班",
    12: "午餐外出",
    13: "午餐返回",
    21: "下班回家",
}


def _find_nearest_forecast(hourly: list[dict], target_hour: int) -> dict | None:
    """从逐时预报中找到最接近目标小时的记录。"""
    best = None
    best_diff = 999
    for h in hourly:
        t = h.get("time", "")
        try:
            hour = int(t.split(" ")[1].split(":")[0])
        except (IndexError, ValueError):
            continue
        diff = abs(hour - target_hour)
        if diff < best_diff:
            best_diff = diff
            best = h
    return best


def _build_weather_summary(data: dict) -> str:
    """从 API 响应构建精简的天气摘要文本。"""
    lines = []

    # 当前天气概况
    city = data.get("city", "未知")
    weather = data.get("weather", "")
    temp = data.get("temperature", "")
    feels = data.get("feels_like", "")
    humidity = data.get("humidity", "")
    wind_dir = data.get("wind_direction", "")
    wind_power = data.get("wind_power", "")
    uv = data.get("uv", "")
    aqi = data.get("aqi", "")
    aqi_cat = data.get("aqi_category", "")

    lines.append(f"城市：{city}")
    lines.append(f"当前天气：{weather}，气温 {temp}°C，体感 {feels}°C")
    lines.append(f"风向：{wind_dir} {wind_power}，湿度 {humidity}%")
    lines.append(f"紫外线指数：{uv}，空气质量：{aqi}（{aqi_cat}）")

    # 关键时段预报
    hourly = data.get("hourly_forecast", [])
    if hourly:
        lines.append("")
        lines.append("关键时段预报：")
        for hour, label in sorted(_KEY_HOURS.items()):
            fc = _find_nearest_forecast(hourly, hour)
            if fc:
                fc_weather = fc.get("weather", "")
                fc_temp = fc.get("temperature", "")
                fc_feels = fc.get("feels_like", "")
                fc_wind = fc.get("wind_direction", "")
                fc_wind_scale = fc.get("wind_scale", "")
                fc_pop = fc.get("pop", 0)
                fc_precip = fc.get("precip", 0)
                line = f"  {hour}:00（{label}）：{fc_weather} {fc_temp}°C 体感{fc_feels}°C {fc_wind}{fc_wind_scale}"
                if fc_pop and int(fc_pop) > 0:
                    line += f" 降水概率{fc_pop}%"
                if fc_precip and float(fc_precip) > 0:
                    line += f" 降水量{fc_precip}mm"
                lines.append(line)

    return "\n".join(lines)


def fetch_weather(config: WeatherConfig) -> Optional[str]:
    """
    获取天气数据并返回精简摘要文本。
    失败返回 None（不阻断 pipeline）。
    """
    url = config.api_url
    params = {
        "city": config.city,
        "adcode": config.adcode,
        "extended": "true",
        "hourly": "true",
        "lang": "zh",
    }
    headers = {}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    try:
        with httpx.Client(timeout=httpx.Timeout(15)) as client:
            resp = client.get(url, params=params, headers=headers)
            logger.info(
                "[weather] city=%s status=%s size=%d",
                config.city, resp.status_code, len(resp.content),
            )
            logger.debug("[weather] body=%s", resp.text[:2000])
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("[weather] fetch failed: %s", e)
        return None

    summary = _build_weather_summary(data)
    logger.info("[weather] summary built, length=%d", len(summary))
    return summary
