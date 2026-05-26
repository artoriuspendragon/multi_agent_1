"""
MiniMax chatcompletion_v2 调用封装。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

_RETRYABLE_STATUS_CODES = {1000, 1001, 1002, 1013}  # MiniMax 已知的可重试错误码
_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 5

import httpx

logger = logging.getLogger(__name__)

DEFAULT_MINIMAX_ENDPOINT = "https://api.minimaxi.com/v1/text/chatcompletion_v2"


def _mask_secret(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) <= 10:
        return "*" * len(v)
    return f"{v[:6]}...{v[-4:]}"


def call_minimax_chat(
    *,
    endpoint: str | None,
    api_key: str,
    model: str,
    system_name: str,
    user_name: str,
    user_content: str,
    timeout_seconds: int,
    max_tokens: int | None = None,
) -> str:
    """
    调用 OpenAI 兼容的 chat completions 接口（MiniMax chatcompletion_v2 / DeepSeek 等），
    返回 choices[0].message.content 文本。

    system_name 作为 system message 的 content（系统指令）。
    max_tokens：最大输出 token；推理类模型（如 DeepSeek v4）建议显式设置以免被默认值截断。
    """
    url = (endpoint or DEFAULT_MINIMAX_ENDPOINT).strip()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_name, "name": "系统"},
            {"role": "user", "content": user_content, "name": user_name},
        ],
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    request_log = {
        "url": url,
        "timeout_seconds": timeout_seconds,
        "headers": {
            "Content-Type": headers.get("Content-Type", ""),
            "Authorization": f"Bearer {_mask_secret(api_key)}",
        },
        "payload": payload,
    }
    logger.info(
        "minimax request detail=%s",
        json.dumps(request_log, ensure_ascii=False),
    )

    last_error: Exception | None = None
    with httpx.Client(timeout=httpx.Timeout(timeout_seconds)) as client:
        for attempt in range(1, _MAX_RETRIES + 1):
            start = time.perf_counter()
            resp = client.post(url, headers=headers, json=payload)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            response_log = {
                "status_code": resp.status_code,
                "elapsed_ms": elapsed_ms,
                "headers": dict(resp.headers),
                "body": resp.text,
            }
            logger.info(
                "minimax response detail=%s",
                json.dumps(response_log, ensure_ascii=False),
            )
            resp.raise_for_status()
            try:
                data = resp.json()
            except Exception as e:
                logger.exception("minimax response is not valid json")
                raise ValueError(f"minimax response json decode failed: {e}") from e

            # 检查 MiniMax 业务层错误码
            base_resp = data.get("base_resp") or {}
            mm_status = base_resp.get("status_code", 0)
            mm_msg = base_resp.get("status_msg", "")
            if mm_status in _RETRYABLE_STATUS_CODES or data.get("choices") is None:
                last_error = ValueError(f"invalid minimax response schema: {data}")
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "minimax transient error (attempt %d/%d) status_code=%s msg=%s, retrying in %ds...",
                        attempt, _MAX_RETRIES, mm_status, mm_msg, _RETRY_DELAY_SECONDS,
                    )
                    time.sleep(_RETRY_DELAY_SECONDS)
                    continue
                else:
                    logger.error(
                        "minimax failed after %d attempts, last error: status_code=%s msg=%s",
                        _MAX_RETRIES, mm_status, mm_msg,
                    )
                    raise last_error

            try:
                content = str(data["choices"][0]["message"]["content"]).strip()
                logger.info(
                    "minimax parsed content length=%d content=%s",
                    len(content),
                    content,
                )
                return content
            except Exception as e:
                logger.exception("invalid minimax response schema")
                raise ValueError(f"invalid minimax response schema: {data}") from e

    raise last_error or ValueError("minimax: no response after retries")


def extract_json_object(text: str) -> dict[str, Any]:
    """
    从文本中提取 JSON object（兼容 ```json ... ``` 包裹）。
    先尝试标准解析，失败时用 json-repair 修复畸形/截断的 JSON。
    """
    s = text.strip()
    # 去掉 markdown 代码块包裹
    if s.startswith("```"):
        s = s.strip("`")
        if s.startswith("json"):
            s = s[4:].strip()

    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("no json object found in text")

    raw = s[start : end + 1]

    # 第一步：标准解析
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError("json root must be object")
        return obj
    except json.JSONDecodeError as e:
        logger.warning("json parse failed (%s), trying json-repair...", e)

    # 第二步：json-repair 修复
    try:
        from json_repair import repair_json
        repaired = repair_json(raw, return_objects=True)
        if isinstance(repaired, dict):
            logger.info("json-repair succeeded")
            return repaired
        # repair_json 返回字符串时再 loads 一次
        if isinstance(repaired, str):
            obj = json.loads(repaired)
            if isinstance(obj, dict):
                logger.info("json-repair succeeded (string path)")
                return obj
    except Exception as repair_err:
        logger.warning("json-repair also failed: %s", repair_err)

    raise ValueError(f"failed to parse json from text (len={len(raw)})")
