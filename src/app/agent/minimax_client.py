"""
MiniMax chatcompletion_v2 调用封装。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

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
) -> str:
    """
    调用 MiniMax chatcompletion_v2，返回 choices[0].message.content 文本。

    system_name 作为 system message 的 content（系统指令）。
    """
    url = (endpoint or DEFAULT_MINIMAX_ENDPOINT).strip()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_name, "name": "系统"},
            {"role": "user", "content": user_content, "name": user_name},
        ],
    }

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

    start = time.perf_counter()
    with httpx.Client(timeout=httpx.Timeout(timeout_seconds)) as client:
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


def extract_json_object(text: str) -> dict[str, Any]:
    """
    从文本中提取 JSON object（兼容 ```json ... ``` 包裹）。
    """
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.startswith("json"):
            s = s[4:].strip()

    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("no json object found in text")
    obj = json.loads(s[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("json root must be object")
    return obj
