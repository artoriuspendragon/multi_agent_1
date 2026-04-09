"""单元测试：push 模块（email/bark）。"""

from __future__ import annotations

from app.config import ChannelConfig, PushConfig
from app.models import Digest, RenderedDigest, Section
from app.push import send_all


def _fake_digest() -> Digest:
    return Digest(
        id="d1",
        title="每日早报 2025-02-15",
        generated_at="2025-02-15T07:00:00+00:00",
        sections=[Section(name="s1", items=[])],
        rendered=RenderedDigest(markdown="# test", text="# test", html=None),
    )


def test_push_email(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=30):
            sent["host"] = host
            sent["port"] = port
            sent["timeout"] = timeout

        def ehlo(self):
            sent["ehlo"] = True

        def starttls(self):
            sent["starttls"] = True

        def login(self, user, password):
            sent["login"] = (user, password)

        def sendmail(self, from_addr, to_addrs, msg):
            sent["from"] = from_addr
            sent["to"] = to_addrs
            sent["msg"] = msg

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    import app.push.email as email_mod

    monkeypatch.setattr(email_mod.smtplib, "SMTP", FakeSMTP)

    digest = _fake_digest()
    cfg = PushConfig(
        channels=[
            ChannelConfig(
                type="email",
                enabled=True,
                smtp_host="smtp.example.com",
                smtp_port=587,
                smtp_user="user",
                smtp_password="pass",
                to="me@example.com",
                use_tls=True,
            )
        ]
    )

    results = send_all(digest, cfg)
    assert results[0].channel_type == "email"
    assert results[0].success is True
    assert "每日早报" in sent["msg"]
    assert sent["to"] == ["me@example.com"]


def test_push_bark(monkeypatch):
    called = {}

    class FakeResponse:
        def __init__(self):
            self.status_code = 200

        def raise_for_status(self):
            return None

    class FakeHttpClient:
        def __init__(self, timeout=None):
            called["timeout"] = timeout

        def get(self, url):
            called["url"] = url
            return FakeResponse()

        def close(self):
            called["closed"] = True

    import app.push.base as base_mod
    monkeypatch.setattr(base_mod.httpx, "Client", FakeHttpClient)

    digest = _fake_digest()
    cfg = PushConfig(
        channels=[
            ChannelConfig(type="bark", enabled=True, base_url="https://api.day.app", key="bark-key")
        ]
    )

    results = send_all(digest, cfg)
    assert results[0].channel_type == "bark"
    assert results[0].success is True
    assert "bark-key" in called["url"]
    assert "每日早报" in called["url"]


def test_push_msgraph(monkeypatch):
    called = {"posts": []}

    class FakeResponse:
        def __init__(self, json_data=None):
            self._json_data = json_data or {}
            self.status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return self._json_data

    class FakeHttpClient:
        def __init__(self, timeout=None):
            called["timeout"] = timeout

        def post(self, url, headers=None, data=None, json=None):
            called["posts"].append({"url": url, "headers": headers, "data": data, "json": json})
            if "oauth2/v2.0/token" in url:
                return FakeResponse({"access_token": "fake-token", "refresh_token": "fake-refresh"})
            return FakeResponse({})

        def close(self):
            called["closed"] = True

    import app.push.base as base_mod
    import app.push.msgraph as msgraph_mod

    monkeypatch.setattr(base_mod.httpx, "Client", FakeHttpClient)

    # 模拟已有缓存 token（跳过 device code flow）
    monkeypatch.setattr(
        msgraph_mod, "_load_cached_token",
        lambda: {"refresh_token": "cached-refresh", "access_token": "old-token"},
    )
    saved_tokens = {}
    monkeypatch.setattr(msgraph_mod, "_save_token", lambda data: saved_tokens.update(data))

    digest = _fake_digest()
    cfg = PushConfig(
        channels=[
            ChannelConfig(
                type="msgraph",
                enabled=True,
                graph_client_id="cid",
                to="recv@outlook.com",
            )
        ]
    )

    results = send_all(digest, cfg)
    assert results[0].channel_type == "msgraph"
    assert results[0].success is True
    assert len(called["posts"]) == 2
    # 第一个请求是 refresh token
    assert "oauth2/v2.0/token" in called["posts"][0]["url"]
    # 第二个请求是 /me/sendMail
    assert "/me/sendMail" in called["posts"][1]["url"]

