"""
API Fetcher：调用 REST API endpoint，解析 JSON 并映射为 RawItem 列表。

由于 PRD 没有对 API 响应结构做强约束，这里实现“宽松映射”：
支持以下 JSON 形态：
- 顶层为 list
- 顶层为 dict，并包含 items / data / results 字段
- 顶层为 dict，作为单条 item 处理
每个 item 通过 title/link/summary/id/raw_id 等字段映射为 RawItem。
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any

import httpx

from app.config import SourceConfig
from app.models import RawItem

from .base import FetcherError, make_item_ids, normalize_url, parse_datetime

logger = logging.getLogger(__name__)
_DEFAULT_ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
_GITHUB_REPO_PATTERN = re.compile(
    r"https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)"
)
_ORAL_PATTERNS = (" oral", "oral presentation", "spotlight")
_MAIN_PATTERNS = (" main", "main track", "main conference")
_FINDINGS_PATTERNS = (" findings",)
_WORKSHOP_PATTERNS = (" workshop", "workshops", "symposium")
_SUBMITTED_PATTERNS = (" submitted to", "under review")
_VENUE_SCORE_RULES: list[tuple[str, float]] = [
    ("neurips", 10.0),
    ("icml", 10.0),
    ("iclr", 10.0),
    ("cvpr", 9.5),
    ("iccv", 9.5),
    ("eccv", 9.5),
    ("acl", 9.0),
    ("emnlp", 9.0),
    ("naacl", 8.8),
    ("coling", 8.2),
    ("aaai", 8.8),
    ("ijcai", 8.8),
    ("kdd", 9.0),
    ("www", 8.8),
    ("the web conference", 8.8),
    ("sigir", 8.8),
    ("aistats", 8.6),
    ("icassp", 8.4),
    ("icra", 8.5),
    ("rss", 8.3),
]


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for k in ("items", "data", "results", "list"):
            v = payload.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        # 单条
        if payload:
            return [payload]
    return []


def _extract_comment(item: dict[str, Any], fields: list[str]) -> str | None:
    for key in fields:
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if val is not None:
            s = str(val).strip()
            if s:
                return s
    return None


def _keep_by_comment_mode(comment: str | None, mode: str) -> bool:
    if mode == "with_comment":
        return bool(comment)
    if mode == "without_comment":
        return not bool(comment)
    return True


def _keep_by_comment_tier(comment: str | None, source: SourceConfig) -> bool:
    if not source.comment_tier_filter_enabled:
        return True
    if not comment:
        return False

    keywords = [k.strip().lower() for k in source.comment_tier_keywords if k.strip()]
    if not keywords:
        # 开启 tier 过滤但未提供关键词：默认不过滤，避免误伤
        return True

    c = comment.lower()
    if source.comment_tier_match_mode == "all":
        return all(k in c for k in keywords)
    return any(k in c for k in keywords)


def _comment_quality_score(comment: str | None) -> float:
    if not comment:
        return 0.0
    c = comment.lower()
    if any(p in c for p in _SUBMITTED_PATTERNS):
        return 0.0
    if any(p in c for p in _ORAL_PATTERNS):
        return 10.0
    if any(p in c for p in _MAIN_PATTERNS):
        return 8.0
    if any(p in c for p in _FINDINGS_PATTERNS):
        return 5.0
    if any(p in c for p in _WORKSHOP_PATTERNS):
        return 3.0
    if "accepted" in c:
        return 7.0
    return 2.0


def _venue_quality_score(comment: str | None, source: SourceConfig) -> float:
    if not comment:
        return 0.0
    c = comment.lower()
    best = 0.0
    for key, score in _VENUE_SCORE_RULES:
        if key in c and score > best:
            best = score
    if best > 0:
        return best
    # 回退：如果命中用户配置的 tier 关键词，给中高分
    keywords = [k.strip().lower() for k in source.comment_tier_keywords if k.strip()]
    if any(k in c for k in keywords):
        return 8.0
    return 0.0


def _github_stars_score(stars: int | None) -> float:
    if not stars or stars <= 0:
        return 0.0
    # 0-10 对数归一化：100 -> 5, 1k -> 7.5, 10k -> 10
    return max(0.0, min(10.0, math.log10(stars + 1) * 2.5))


def _extract_arxiv_id(item: dict[str, Any], link: str, raw_id: str) -> str | None:
    candidates = [
        str(item.get("arxiv_id") or "").strip(),
        str(item.get("id") or "").strip(),
        link.strip(),
        raw_id.strip(),
    ]
    for c in candidates:
        if not c:
            continue
        m = re.search(r"arxiv\.org/abs/([A-Za-z0-9.\-_/]+)", c)
        if m:
            aid = m.group(1)
            return re.sub(r"v\d+$", "", aid)
        m = re.search(r"^([0-9]{4}\.[0-9]{4,5})(v\d+)?$", c)
        if m:
            return m.group(1)
    return None


def _extract_doi(item: dict[str, Any]) -> str | None:
    for key in ("doi", "arxiv_doi", "dc:identifier"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            v = val.strip()
            if "doi.org/" in v:
                v = v.split("doi.org/", 1)[1]
            return v
    return None


def _fetch_semantic_scholar_citations(
    *,
    arxiv_id: str | None,
    doi: str | None,
    source: SourceConfig,
    client: httpx.Client,
    cache: dict[str, int | None],
) -> int | None:
    if not source.semantic_scholar_enabled:
        return None
    key = arxiv_id or (f"doi:{doi}" if doi else "")
    if not key:
        return None
    if key in cache:
        return cache[key]

    api_base = source.semantic_scholar_api_url.rstrip("/")
    paper_id = f"ARXIV:{arxiv_id}" if arxiv_id else f"DOI:{doi}"
    url = f"{api_base}/paper/{paper_id}"
    headers = {"Accept": "application/json"}
    sk = (source.semantic_scholar_api_key or "").strip()
    if sk:
        headers["x-api-key"] = sk
    params = {"fields": "citationCount,influentialCitationCount"}

    try:
        resp = client.get(url, headers=headers, params=params, timeout=httpx.Timeout(source.crossref_timeout_seconds))
        if resp.status_code == 404:
            cache[key] = None
            return None
        resp.raise_for_status()
        data = resp.json()
        cited = int(data.get("citationCount", 0))
        infl = int(data.get("influentialCitationCount", 0))
        # 适度放大高质量引用信号
        total = cited + infl * 2
        cache[key] = total
        return total
    except Exception as e:
        logger.warning("[api] semantic scholar lookup failed key=%s err=%s", key, e)
        cache[key] = None
        return None


def _fetch_openalex_citations(
    *,
    arxiv_id: str | None,
    doi: str | None,
    source: SourceConfig,
    client: httpx.Client,
    cache: dict[str, int | None],
) -> int | None:
    if not source.openalex_enabled:
        return None
    key = arxiv_id or (f"doi:{doi}" if doi else "")
    if not key:
        return None
    cache_key = f"oa:{key}"
    if cache_key in cache:
        return cache[cache_key]

    api_base = source.openalex_api_url.rstrip("/")
    url = f"{api_base}/works"
    if doi:
        filt = f"doi:{doi}"
    elif arxiv_id:
        filt = f"locations.landing_page_url:https://arxiv.org/abs/{arxiv_id}"
    else:
        return None
    params = {"filter": filt, "per-page": "1"}

    try:
        resp = client.get(url, params=params, timeout=httpx.Timeout(source.crossref_timeout_seconds))
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results")
        if not isinstance(results, list) or not results:
            cache[cache_key] = None
            return None
        cited = int((results[0] or {}).get("cited_by_count", 0))
        cache[cache_key] = cited
        return cited
    except Exception as e:
        logger.warning("[api] openalex lookup failed key=%s err=%s", key, e)
        cache[cache_key] = None
        return None


def _crossref_quality_score(
    *,
    arxiv_id: str | None,
    doi: str | None,
    source: SourceConfig,
    client: httpx.Client,
    ss_cache: dict[str, int | None],
    oa_cache: dict[str, int | None],
) -> tuple[float, int | None]:
    if not source.crossref_enabled:
        return 0.0, None

    ss = _fetch_semantic_scholar_citations(
        arxiv_id=arxiv_id,
        doi=doi,
        source=source,
        client=client,
        cache=ss_cache,
    )
    oa = _fetch_openalex_citations(
        arxiv_id=arxiv_id,
        doi=doi,
        source=source,
        client=client,
        cache=oa_cache,
    )
    vals = [v for v in (ss, oa) if v is not None]
    if not vals:
        return 0.0, None
    merged = max(vals)
    score = max(0.0, min(10.0, math.log10(merged + 1) * 3.0))
    return score, merged


def _final_quality_score(
    *,
    comment_score: float,
    venue_score: float,
    github_score: float,
    crossref_score: float,
    source: SourceConfig,
) -> float:
    w_comment = source.quality_weight_comment
    w_venue = source.quality_weight_venue
    w_github = source.quality_weight_github
    w_cross = source.quality_weight_crossref
    total_w = w_comment + w_venue + w_github + w_cross
    if total_w <= 0:
        return 0.0
    score = (
        comment_score * w_comment
        + venue_score * w_venue
        + github_score * w_github
        + crossref_score * w_cross
    ) / total_w
    return max(0.0, min(10.0, score))


def _parse_feed_entries(content: bytes) -> list[dict[str, Any]]:
    try:
        import feedparser
    except Exception as e:
        raise FetcherError(f"feedparser import failed: {e}") from e
    feed = feedparser.parse(content)
    out: list[dict[str, Any]] = []
    for entry in getattr(feed, "entries", []) or []:
        if isinstance(entry, dict):
            out.append(entry)
    return out


def _extract_github_repos(item: dict[str, Any], comment: str | None, summary: str | None) -> list[str]:
    texts: list[str] = []
    if comment:
        texts.append(comment)
    if summary:
        texts.append(summary)
    for k in ("link", "url", "href"):
        v = item.get(k)
        if isinstance(v, str) and v:
            texts.append(v)
    links = item.get("links")
    if isinstance(links, list):
        for row in links:
            if isinstance(row, dict):
                for lk in ("href", "link", "url"):
                    lv = row.get(lk)
                    if isinstance(lv, str) and lv:
                        texts.append(lv)
            elif isinstance(row, str) and row:
                texts.append(row)

    repos: list[str] = []
    seen: set[str] = set()
    for txt in texts:
        for m in _GITHUB_REPO_PATTERN.finditer(txt):
            owner = m.group(1).strip().lower()
            repo = m.group(2).strip()
            repo = repo.removesuffix(".git").strip().lower()
            if not owner or not repo:
                continue
            full = f"{owner}/{repo}"
            if full in seen:
                continue
            seen.add(full)
            repos.append(full)
    return repos


def _fetch_github_repo_stars(
    *,
    repo: str,
    source: SourceConfig,
    client: httpx.Client,
    cache: dict[str, int | None],
) -> int | None:
    if repo in cache:
        return cache[repo]

    api_base = source.github_api_url.rstrip("/")
    url = f"{api_base}/repos/{repo}"
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    token = (source.github_token or "").strip()
    has_unresolved_placeholder = ("${" in token) or token.startswith("$")
    use_auth = bool(token) and not has_unresolved_placeholder
    if use_auth:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = client.get(url, headers=headers, timeout=httpx.Timeout(source.github_timeout_seconds))
        if resp.status_code == 401 and use_auth:
            # token 无效/过期时，公开仓库可尝试匿名读取，避免整条数据被误杀
            logger.warning(
                "[api] github auth failed (401), retrying without token repo=%s",
                repo,
            )
            resp = client.get(
                url,
                headers={"Accept": "application/vnd.github+json"},
                timeout=httpx.Timeout(source.github_timeout_seconds),
            )
        if resp.status_code == 404:
            cache[repo] = None
            return None
        resp.raise_for_status()
        payload = resp.json()
        stars = int(payload.get("stargazers_count", 0))
        cache[repo] = stars
        return stars
    except Exception as e:
        logger.warning("[api] github stars lookup failed repo=%s err=%s", repo, e)
        cache[repo] = None
        return None


class ApiFetcher:
    def fetch(self, source: SourceConfig, client: httpx.Client) -> list[RawItem]:
        endpoint = source.endpoint
        if source.type == "arxiv" and not endpoint:
            endpoint = _DEFAULT_ARXIV_ENDPOINT

        if not endpoint:
            raise FetcherError("api source requires endpoint")

        try:
            resp = client.get(
                endpoint,
                params=source.params,
                headers=source.headers,
            )
            logger.info(
                "[api] source=%s endpoint=%s status=%s size=%d",
                source.id, endpoint, resp.status_code, len(resp.content),
            )
            logger.debug("[api] source=%s body=%s", source.id, resp.text[:2000])
            resp.raise_for_status()
        except Exception as e:
            raise FetcherError(f"api request failed: {e}") from e

        mode = source.response_format
        if mode == "auto":
            ctype = (resp.headers.get("Content-Type") or "").lower()
            text_head = (resp.text or "").lstrip()[:40].lower()
            if "xml" in ctype or text_head.startswith("<?xml") or "<feed" in text_head or "<rss" in text_head:
                mode = "feed"
            else:
                mode = "json"

        records: list[dict[str, Any]]
        if mode == "json":
            try:
                payload = resp.json()
            except Exception as e:
                raise FetcherError(f"api response is not json: {e}") from e
            records = _extract_items(payload)
        else:
            records = _parse_feed_entries(resp.content)

        items: list[RawItem] = []
        github_cache: dict[str, int | None] = {}
        ss_cache: dict[str, int | None] = {}
        oa_cache: dict[str, int | None] = {}
        for item in records:
            title = str(item.get("title") or item.get("name") or "").strip()
            link = item.get("link") or item.get("url") or item.get("href") or item.get("permalink")
            link = normalize_url(endpoint, str(link) if link is not None else None)
            if not link:
                continue

            # summary 兜底：顶层字段 → extra.desc（如知乎热榜）
            extra_data = item.get("extra") if isinstance(item.get("extra"), dict) else {}
            summary = (
                item.get("summary")
                or item.get("description")
                or item.get("content")
                or extra_data.get("desc")
                or None
            )
            if isinstance(summary, str):
                summary = summary.strip() or None
            else:
                summary = str(summary) if summary is not None else None

            # feed 模式常见 comment 字段（例如 arXiv 的 arxiv_comment）
            comment = _extract_comment(item, source.comment_fields)
            if not _keep_by_comment_mode(comment, source.comment_mode):
                continue
            if not _keep_by_comment_tier(comment, source):
                continue

            github_repos: list[str] = []
            github_best_repo: str | None = None
            github_best_stars: int | None = None
            if source.github_filter_enabled:
                github_repos = _extract_github_repos(item, comment, summary)
                if source.github_require_repo and not github_repos:
                    continue
                for repo in github_repos:
                    stars = _fetch_github_repo_stars(
                        repo=repo,
                        source=source,
                        client=client,
                        cache=github_cache,
                    )
                    if stars is None:
                        continue
                    if github_best_stars is None or stars > github_best_stars:
                        github_best_stars = stars
                        github_best_repo = repo
                if source.github_stars_min > 0:
                    if github_best_stars is None or github_best_stars < source.github_stars_min:
                        continue

            raw_id = (
                item.get("raw_id")
                or item.get("id")
                or item.get("guid")
                or item.get("published_id")
                or link
            )
            published_at = parse_datetime(item.get("published_at") or item.get("published") or item.get("pubDate") or item.get("date"))

            item_id, raw_id = make_item_ids(source.id, str(raw_id), link)
            extra = item if isinstance(item, dict) else {}
            if isinstance(extra, dict):
                extra = dict(extra)
                extra["comment"] = comment
                extra["has_comment"] = bool(comment)
                if source.github_filter_enabled:
                    extra["github_repos"] = github_repos
                    extra["github_repo"] = github_best_repo
                    extra["github_stars"] = github_best_stars
                if source.quality_score_enabled:
                    arxiv_id = _extract_arxiv_id(item, link=link, raw_id=str(raw_id))
                    doi = _extract_doi(item)
                    comment_score = _comment_quality_score(comment)
                    venue_score = _venue_quality_score(comment, source)
                    github_score = _github_stars_score(github_best_stars)
                    crossref_score, crossref_citations = _crossref_quality_score(
                        arxiv_id=arxiv_id,
                        doi=doi,
                        source=source,
                        client=client,
                        ss_cache=ss_cache,
                        oa_cache=oa_cache,
                    )
                    final_score = _final_quality_score(
                        comment_score=comment_score,
                        venue_score=venue_score,
                        github_score=github_score,
                        crossref_score=crossref_score,
                        source=source,
                    )
                    extra["quality_score"] = round(final_score, 4)
                    extra["quality_breakdown"] = {
                        "comment": round(comment_score, 4),
                        "venue": round(venue_score, 4),
                        "github": round(github_score, 4),
                        "crossref": round(crossref_score, 4),
                    }
                    extra["crossref_citations"] = crossref_citations
                    extra["arxiv_id"] = arxiv_id
                    if doi:
                        extra["doi"] = doi
            items.append(
                RawItem(
                    id=item_id,
                    source_id=source.id,
                    raw_id=str(raw_id),
                    title=title or link,
                    link=link,
                    summary=summary,
                    published_at=published_at,
                    extra=extra,
                )
            )

        if source.quality_score_enabled:
            items.sort(
                key=lambda x: float(
                    x.extra.get("quality_score", 0.0) if isinstance(x.extra, dict) else 0.0
                ),
                reverse=True,
            )
            if source.quality_score_min > 0:
                items = [
                    it
                    for it in items
                    if float(
                        it.extra.get("quality_score", 0.0) if isinstance(it.extra, dict) else 0.0
                    )
                    >= source.quality_score_min
                ]
            if source.quality_score_top_k > 0:
                items = items[: source.quality_score_top_k]

        return items
