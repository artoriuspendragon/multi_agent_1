"""单元测试：config 模块（环境变量替换、load_config、校验）。"""

import tempfile
from pathlib import Path

import pytest

from app.config import (
    AppConfig,
    ChannelConfig,
    ConfigLoadError,
    DigestConfig,
    FilterConfig,
    SourceConfig,
    load_config,
    _substitute_env,
)


def test_substitute_env_string():
    out = _substitute_env("hello ${FOO} bar", {"FOO": "world"})
    assert out == "hello world bar"


def test_substitute_env_missing_var_left_as_is():
    out = _substitute_env("hello ${MISSING} bar", {})
    assert out == "hello ${MISSING} bar"


def test_substitute_env_nested_dict():
    data = {"a": {"b": "val=${X}"}, "c": ["${Y}"]}
    out = _substitute_env(data, {"X": "1", "Y": "2"})
    assert out["a"]["b"] == "val=1"
    assert out["c"][0] == "2"


def test_source_config_rss_requires_url():
    with pytest.raises(ValueError, match="requires 'url'"):
        SourceConfig(id="s1", type="rss", endpoint="https://x.com")
    ok = SourceConfig(id="s1", type="rss", url="https://example.com/feed.xml")
    assert ok.type == "rss"


def test_source_config_api_requires_endpoint():
    with pytest.raises(ValueError, match="requires 'endpoint'"):
        SourceConfig(id="s2", type="api", url="https://x.com")
    ok = SourceConfig(id="s2", type="api", endpoint="https://api.example.com/news")
    assert ok.type == "api"


def test_filter_config_defaults():
    f = FilterConfig()
    assert f.strategy == "rule"
    assert f.exclude_keywords == []
    assert f.sort_by == "published_at"
    assert f.agent is None


def test_channel_config_bark_requires_key():
    with pytest.raises(ValueError, match="bark.*requires key"):
        ChannelConfig(type="bark", enabled=True)
    ok = ChannelConfig(type="bark", key="my-key")
    assert ok.base_url == "https://api.day.app"


def test_channel_config_email_requires_smtp_host_and_to():
    with pytest.raises(ValueError, match="email.*requires smtp_host and to"):
        ChannelConfig(type="email", enabled=True)
    ok = ChannelConfig(type="email", smtp_host="smtp.x.com", to="u@x.com")
    assert ok.smtp_host == "smtp.x.com"


def test_load_config_file_not_found():
    with pytest.raises(ConfigLoadError, match="not found"):
        load_config(path="/nonexistent/config.yaml")


def test_load_config_success_minimal(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        """
sources:
  - id: r1
    type: rss
    url: https://example.com/feed.xml
filter:
  strategy: rule
digest:
  strategy: template
push:
  channels: []
""",
        encoding="utf-8",
    )
    app = load_config(path=cfg_path)
    assert len(app.sources) == 1
    assert app.sources[0].id == "r1"
    assert app.filter.strategy == "rule"
    assert app.digest.strategy == "template"
    assert app.push.channels == []


def test_load_config_env_substitution(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        """
sources:
  - id: r1
    type: rss
    url: https://example.com/feed.xml
filter:
  strategy: rule
digest:
  strategy: template
push:
  channels:
    - type: bark
      key: ${BARK_KEY}
""",
        encoding="utf-8",
    )
    app = load_config(path=cfg_path, env={"BARK_KEY": "secret-key"})
    assert app.push.channels[0].key == "secret-key"


def test_load_config_validation_fail_unknown_source_type(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        """
sources:
  - id: r1
    type: unknown_type
    url: https://example.com/feed.xml
filter:
  strategy: rule
digest:
  strategy: template
push:
  channels: []
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigLoadError, match="validation failed"):
        load_config(path=cfg_path)


def test_app_config_requires_filter_agent_when_strategy_agent():
    from app.config import PushConfig

    with pytest.raises(ValueError, match="filter.agent is not set"):
        AppConfig(
            sources=[],
            filter=FilterConfig(strategy="agent"),
            digest=DigestConfig(),
            push=PushConfig(channels=[]),
        )
