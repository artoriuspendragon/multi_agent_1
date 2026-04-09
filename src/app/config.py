"""
配置加载、环境变量替换与 Pydantic 校验。

对外暴露：load_config(path, env) -> AppConfig
凭证仅通过环境变量注入，配置文件中使用占位符如 ${VAR}。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal, Optional, Union

import yaml
from pydantic import BaseModel, Field, model_validator

# 占位符：${VAR} 或 $VAR（单词边界）
_ENV_PATTERN = re.compile(r"\$\{(\w+)\}|\$(\w+)")


def _substitute_env(value: Any, env: dict[str, str]) -> Any:
    """递归对配置中的字符串做 ${VAR} / $VAR 替换。未找到的变量保留原样。"""
    if isinstance(value, str):
        def repl(m: re.Match[str]) -> str:
            key = m.group(1) or m.group(2) or ""
            return env.get(key, m.group(0))

        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _substitute_env(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(item, env) for item in value]
    return value


# ---------- 信息源 ----------


class SourceConfig(BaseModel):
    """单条信息源配置。rss 需 url；api 需 endpoint；crawler 需 url。"""

    id: str
    type: Literal["rss", "api", "crawler", "arxiv"]
    url: Optional[str] = None
    endpoint: Optional[str] = None
    name: Optional[str] = None
    params: Optional[dict[str, str]] = None
    headers: Optional[dict[str, str]] = None
    response_format: Literal["auto", "json", "feed"] = "auto"
    comment_mode: Literal["any", "with_comment", "without_comment"] = "any"
    comment_fields: list[str] = Field(
        default_factory=lambda: ["comment", "arxiv_comment", "arxiv:comment"]
    )
    comment_tier_filter_enabled: bool = False
    comment_tier_keywords: list[str] = Field(default_factory=list)
    comment_tier_match_mode: Literal["any", "all"] = "any"
    github_filter_enabled: bool = False
    github_stars_min: int = Field(default=0, ge=0)
    github_require_repo: bool = False
    github_token: Optional[str] = None
    github_api_url: str = "https://api.github.com"
    github_timeout_seconds: int = Field(default=10, ge=1, le=60)
    quality_score_enabled: bool = False
    quality_score_min: float = Field(default=0.0, ge=0.0, le=10.0)
    quality_score_top_k: int = Field(default=0, ge=0, le=2000)
    quality_weight_comment: float = Field(default=0.35, ge=0.0, le=1.0)
    quality_weight_venue: float = Field(default=0.25, ge=0.0, le=1.0)
    quality_weight_github: float = Field(default=0.20, ge=0.0, le=1.0)
    quality_weight_crossref: float = Field(default=0.20, ge=0.0, le=1.0)
    crossref_enabled: bool = False
    openalex_enabled: bool = True
    openalex_api_url: str = "https://api.openalex.org"
    semantic_scholar_enabled: bool = True
    semantic_scholar_api_url: str = "https://api.semanticscholar.org/graph/v1"
    semantic_scholar_api_key: Optional[str] = None
    crossref_timeout_seconds: int = Field(default=10, ge=1, le=60)
    # crawler 可选：选择器或规则引用
    selector: Optional[str] = None
    # arXiv 可选：基础查询 + 时间范围 + comment 过滤
    arxiv_search_query: Optional[str] = None
    arxiv_start: Optional[str] = None
    arxiv_end: Optional[str] = None
    arxiv_days: int = Field(default=1, ge=1, le=30)
    arxiv_max_results: int = Field(default=100, ge=1, le=1000)
    arxiv_comment_mode: Literal["any", "with_comment", "without_comment"] = "any"

    @model_validator(mode="after")
    def require_url_or_endpoint_by_type(self) -> "SourceConfig":
        if self.type == "rss" or self.type == "crawler":
            if not self.url:
                raise ValueError(f"source type '{self.type}' requires 'url'")
        if self.type == "api":
            if not self.endpoint:
                raise ValueError("source type 'api' requires 'endpoint'")
        if self.type == "arxiv":
            if bool(self.arxiv_start) ^ bool(self.arxiv_end):
                raise ValueError("arxiv source requires both arxiv_start and arxiv_end")
            if self.endpoint is None:
                self.endpoint = "https://export.arxiv.org/api/query"
            if not self.params:
                self.params = {
                    "search_query": "(all:*) AND submittedDate:[{{yesterday:%Y%m%d}}0000 TO {{today:%Y%m%d}}0000]",
                    "start": "0",
                    "max_results": "200",
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }
            if self.response_format == "auto":
                self.response_format = "feed"
        return self


# ---------- 过滤 ----------


class FilterAgentConfig(BaseModel):
    """过滤 Agent 配置（strategy 含 agent 时必填）。"""

    endpoint: str
    api_key: str
    model: str
    user_preference: str
    timeout_seconds: int = Field(default=60, ge=1, le=300)
    max_items_per_call: int = Field(default=100, ge=1, le=500)
    prompt_template: Optional[str] = None


class FilterConfig(BaseModel):
    """过滤与排序配置。"""

    strategy: Literal["rule", "agent", "rule_then_agent"] = "rule"
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    allowed_sources: list[str] = Field(default_factory=list)
    blocked_sources: list[str] = Field(default_factory=list)
    max_age_hours: Optional[int] = Field(default=24, ge=1, le=720)
    sort_by: Literal["published_at", "title", "source_id"] = "published_at"
    order: Literal["asc", "desc"] = "desc"
    agent: Optional[FilterAgentConfig] = None


# ---------- 早报 ----------


class DigestAgentConfig(BaseModel):
    """早报生成 Agent 配置（strategy 含 agent 时必填）。"""

    endpoint: str
    api_key: str
    model: str
    constraints: str
    output_format: Literal["structured", "rendered"] = "structured"
    timeout_seconds: int = Field(default=120, ge=1, le=600)
    max_input_items: int = Field(default=50, ge=1, le=300)
    include_summary: bool = False
    max_summary_chars: int = Field(default=200, ge=0, le=2000)
    prompt_template: Optional[str] = None


class DigestConfig(BaseModel):
    """早报生成配置。"""

    strategy: Literal["template", "agent", "template_then_agent"] = "template"
    title_template: str = Field(default="每日早报 {{date}}")
    max_items: int = Field(default=50, ge=1, le=500)
    group_by: Literal["source", "tag", "none"] = "source"
    agent: Optional[DigestAgentConfig] = None


# ---------- 天气 ----------


class WeatherConfig(BaseModel):
    """天气 API 配置。"""

    enabled: bool = False
    api_url: str = "https://uapis.cn/api/v1/misc/weather"
    api_key: Optional[str] = None
    city: str = "北京"
    adcode: str = "100085"
    # 用户作息（供 AI 生成穿衣/出行建议）
    schedule: Optional[str] = None


# ---------- 推送渠道（各渠道可选字段放同一模型，按 type 校验） ----------


class ChannelConfig(BaseModel):
    """
    单条推送渠道配置。
    type 决定所需字段：email(smtp_*, to)、bark(base_url, key)、telegram(bot token, chat_id) 等。
    """

    type: Literal["email", "bark", "telegram", "wecom", "dingtalk", "msgraph"]
    enabled: bool = True
    # email
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    to: Optional[str] = None
    use_tls: bool = True
    # bark
    base_url: str = "https://api.day.app"
    key: Optional[str] = None
    # telegram
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    # wecom / dingtalk
    webhook_url: Optional[str] = None
    # msgraph
    graph_tenant_id: Optional[str] = None
    graph_client_id: Optional[str] = None
    graph_client_secret: Optional[str] = None
    graph_sender: Optional[str] = None

    @model_validator(mode="after")
    def require_fields_by_type(self) -> "ChannelConfig":
        t = self.type
        if t == "email":
            if not (self.smtp_host and self.to):
                raise ValueError("channel type 'email' requires smtp_host and to")
            if not self.smtp_user and not self.smtp_password:
                pass  # 允许无认证
        elif t == "bark":
            if not self.key:
                raise ValueError("channel type 'bark' requires key")
        elif t == "telegram":
            if not (self.bot_token and self.chat_id):
                raise ValueError("channel type 'telegram' requires bot_token and chat_id")
        elif t in ("wecom", "dingtalk"):
            if not self.webhook_url:
                raise ValueError(f"channel type '{t}' requires webhook_url")
        elif t == "msgraph":
            if not (self.graph_client_id and self.to):
                raise ValueError(
                    "channel type 'msgraph' requires graph_client_id and to"
                )
        return self


class PushConfig(BaseModel):
    """推送配置：渠道列表。dry_run=true 时跳过实际发送，仅打印日志。"""

    dry_run: bool = False
    channels: list[ChannelConfig] = Field(default_factory=list)


# ---------- 顶层应用配置 ----------


class AppConfig(BaseModel):
    """应用完整配置：sources、filter、digest、push。"""

    sources: list[SourceConfig] = Field(default_factory=list)
    filter: FilterConfig = Field(default_factory=FilterConfig)
    digest: DigestConfig = Field(default_factory=DigestConfig)
    weather: WeatherConfig = Field(default_factory=WeatherConfig)
    push: PushConfig = Field(default_factory=PushConfig)

    @model_validator(mode="after")
    def require_agent_when_strategy_uses_it(self) -> "AppConfig":
        if self.filter.strategy in ("agent", "rule_then_agent") and not self.filter.agent:
            raise ValueError(
                "filter.strategy is '%s' but filter.agent is not set"
                % self.filter.strategy
            )
        if self.digest.strategy in ("agent", "template_then_agent") and not self.digest.agent:
            raise ValueError(
                "digest.strategy is '%s' but digest.agent is not set"
                % self.digest.strategy
            )
        return self


# ---------- 加载入口 ----------


class ConfigLoadError(Exception):
    """配置加载或校验失败时抛出，message 便于人类与 AI 理解。"""

    pass


def load_config(
    path: Optional[Union[str, Path]] = None,
    env: Optional[dict[str, str]] = None,
) -> AppConfig:
    """
    加载配置文件，替换环境变量占位符后做 Pydantic 校验，返回 AppConfig。

    :param path: 配置文件路径（YAML 或 JSON）。None 时使用环境变量 CONFIG_PATH，再否则默认 ./config.yaml。
    :param env: 用于替换 ${VAR} 的键值对。None 时使用 os.environ。
    :return: 校验后的 AppConfig
    :raises ConfigLoadError: 文件不存在、解析失败或校验失败，message 含具体原因
    """
    import os

    env = env if env is not None else dict(os.environ)
    if path is None:
        path = os.environ.get("CONFIG_PATH", "config.yaml")
    path = Path(path)
    if not path.exists():
        raise ConfigLoadError("config file not found: %s" % path)

    raw: dict[str, Any]
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in (".yaml", ".yml"):
            raw = yaml.safe_load(text) or {}
        elif path.suffix.lower() == ".json":
            import json
            raw = json.loads(text)
        else:
            raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise ConfigLoadError("invalid YAML: %s" % e) from e
    except Exception as e:
        raise ConfigLoadError("failed to read config: %s" % e) from e

    if not isinstance(raw, dict):
        raise ConfigLoadError("config root must be a dict")

    substituted = _substitute_env(raw, env)

    try:
        return AppConfig.model_validate(substituted)
    except Exception as e:
        raise ConfigLoadError("config validation failed: %s" % e) from e
