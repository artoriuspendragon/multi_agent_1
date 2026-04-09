"""
Microsoft Graph 邮件发送（Device Code Flow，支持个人 @outlook.com 账户）。

首次运行时会提示用户在浏览器中登录授权，之后通过 refresh_token 自动续期。
token 缓存在项目根目录的 .msgraph_token.json 文件中。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from app.config import ChannelConfig
from app.models import Digest

from .base import _render_for_plain_text

# token 缓存文件路径（项目根目录）
_TOKEN_CACHE_PATH = Path(".msgraph_token.json")

# 个人 Microsoft 账户使用 consumers 端点
_AUTH_BASE = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
_SCOPES = "Mail.Send offline_access"


def _load_cached_token() -> dict | None:
    """从缓存文件加载 token。"""
    if _TOKEN_CACHE_PATH.exists():
        try:
            data = json.loads(_TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("refresh_token"):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _save_token(token_data: dict) -> None:
    """将 token 数据写入缓存文件。"""
    _TOKEN_CACHE_PATH.write_text(
        json.dumps(token_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _refresh_access_token(
    client_id: str,
    refresh_token: str,
    http_client: httpx.Client,
) -> dict:
    """用 refresh_token 换取新的 access_token。"""
    resp = http_client.post(
        f"{_AUTH_BASE}/token",
        data={
            "client_id": client_id,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": _SCOPES,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    return resp.json()


def _device_code_flow(
    client_id: str,
    http_client: httpx.Client,
) -> dict:
    """执行 Device Code Flow，需要用户在浏览器中授权。"""
    # 1. 请求 device code
    dc_resp = http_client.post(
        f"{_AUTH_BASE}/devicecode",
        data={
            "client_id": client_id,
            "scope": _SCOPES,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    dc_resp.raise_for_status()
    dc_data = dc_resp.json()

    device_code = dc_data["device_code"]
    user_code = dc_data["user_code"]
    verification_uri = dc_data["verification_uri"]
    interval = dc_data.get("interval", 5)
    expires_in = dc_data.get("expires_in", 900)

    # 2. 提示用户
    print("\n" + "=" * 60)
    print("Microsoft 账户授权")
    print(f"请在浏览器中打开: {verification_uri}")
    print(f"输入代码: {user_code}")
    print("=" * 60 + "\n")

    # 3. 轮询等待用户授权
    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        poll_resp = http_client.post(
            f"{_AUTH_BASE}/token",
            data={
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        poll_data = poll_resp.json()

        if "access_token" in poll_data:
            return poll_data

        error = poll_data.get("error", "")
        if error == "authorization_pending":
            continue
        elif error == "slow_down":
            interval += 5
            continue
        elif error == "authorization_declined":
            raise RuntimeError("用户拒绝了授权")
        elif error == "expired_token":
            raise RuntimeError("授权超时，请重试")
        else:
            raise RuntimeError(f"Device code flow 失败: {poll_data}")

    raise RuntimeError("授权超时，请重试")


def _get_access_token(
    client_id: str,
    http_client: httpx.Client,
) -> str:
    """获取 access_token：优先用缓存的 refresh_token，否则走 device code flow。"""
    cached = _load_cached_token()

    if cached and cached.get("refresh_token"):
        try:
            token_data = _refresh_access_token(
                client_id, cached["refresh_token"], http_client
            )
            _save_token(token_data)
            return token_data["access_token"]
        except httpx.HTTPStatusError:
            # refresh_token 过期，重新走 device code flow
            pass

    # 首次使用或 refresh_token 失效
    token_data = _device_code_flow(client_id, http_client)
    _save_token(token_data)
    return token_data["access_token"]


class MsGraphSender:
    channel_type = "msgraph"

    def send(
        self,
        digest: Digest,
        channel: ChannelConfig,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        if channel.type != "msgraph":
            raise ValueError("MsGraphSender only supports channel.type='msgraph'")
        if not (channel.graph_client_id and channel.to):
            raise ValueError("msgraph channel missing required fields (graph_client_id, to)")

        close_after = False
        if http_client is None:
            http_client = httpx.Client(timeout=httpx.Timeout(30))
            close_after = True

        try:
            access_token = _get_access_token(channel.graph_client_id, http_client)

            body_text = _render_for_plain_text(digest)
            subject = digest.title or "Daily Digest"

            # 使用 /me/sendMail（device code flow 代表登录用户）
            send_url = "https://graph.microsoft.com/v1.0/me/sendMail"
            payload = {
                "message": {
                    "subject": subject,
                    "body": {"contentType": "Text", "content": body_text},
                    "toRecipients": [
                        {"emailAddress": {"address": channel.to}},
                    ],
                },
                "saveToSentItems": "true",
            }

            send_resp = http_client.post(
                send_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            send_resp.raise_for_status()
        finally:
            if close_after:
                http_client.close()
