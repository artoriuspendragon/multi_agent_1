"""单元测试：sources 模块（rss/api/crawler）。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.config import SourceConfig
from app.sources.api import ApiFetcher
from app.sources.crawler import CrawlerFetcher
from app.sources.rss import RSSFetcher


class FakeResponse:
    def __init__(
        self,
        *,
        content: bytes | None = None,
        text: str | None = None,
        json_data=None,
        status_code: int = 200,
    ):
        self.content = content or b""
        self.text = text or ""
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http error: {self.status_code}")

    def json(self):
        return self._json_data


class FakeClient:
    def __init__(self, response: FakeResponse):
        self._response = response
        self.calls = []

    def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self._response


def test_rss_fetcher_maps_basic():
    rss_xml = """<?xml version="1.0" encoding="UTF-8" ?>
    <rss version="2.0">
      <channel>
        <title>Test</title>
        <item>
          <title>Item 1</title>
          <link>https://example.com/i1</link>
          <description>Summary 1</description>
          <pubDate>Sat, 15 Feb 2026 08:00:00 GMT</pubDate>
          <guid>g1</guid>
        </item>
      </channel>
    </rss>"""

    source = SourceConfig(id="rss1", type="rss", url="https://example.com/feed.xml")
    client = FakeClient(FakeResponse(content=rss_xml.encode("utf-8")))
    fetcher = RSSFetcher()
    items = fetcher.fetch(source, client)  # type: ignore[arg-type]

    assert len(items) == 1
    assert items[0].source_id == "rss1"
    assert items[0].title == "Item 1"
    assert items[0].link == "https://example.com/i1"
    assert items[0].summary == "Summary 1"
    assert items[0].raw_id == "g1"
    assert items[0].published_at is not None


def test_api_fetcher_maps_json_items():
    payload = {
        "items": [
            {
                "title": "T1",
                "link": "/i1",
                "summary": "S1",
                "published_at": "2025-02-15T08:00:00Z",
                "raw_id": "r1",
            }
        ]
    }
    source = SourceConfig(id="api1", type="api", endpoint="https://api.example.com/news")
    client = FakeClient(FakeResponse(json_data=payload))
    fetcher = ApiFetcher()
    items = fetcher.fetch(source, client)  # type: ignore[arg-type]

    assert len(items) == 1
    assert items[0].id == "api1:r1"
    assert items[0].raw_id == "r1"
    assert items[0].title == "T1"
    assert items[0].link == "https://api.example.com/i1"
    assert items[0].summary == "S1"
    assert items[0].published_at is not None
    assert items[0].published_at.tzinfo is not None


def test_crawler_fetcher_with_selector():
    html = """<html><head><title>Page</title></head>
    <body>
      <article><a href="/a1">A1</a></article>
      <article><a href="/a2">A2</a></article>
    </body></html>"""

    source = SourceConfig(id="c1", type="crawler", url="https://example.com/page.html", selector="article a")
    client = FakeClient(FakeResponse(text=html))
    fetcher = CrawlerFetcher()
    items = fetcher.fetch(source, client)  # type: ignore[arg-type]

    assert len(items) == 2
    links = {x.link for x in items}
    assert "https://example.com/a1" in links
    assert "https://example.com/a2" in links
    titles = {x.title for x in items}
    assert "A1" in titles
    assert "A2" in titles


def test_api_fetcher_feed_filters_with_comment():
    atom = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>http://arxiv.org/abs/2501.00001v1</id>
        <updated>2026-04-08T00:00:00Z</updated>
        <published>2026-04-08T00:00:00Z</published>
        <title>Paper A</title>
        <summary>Abstract A</summary>
        <link href="http://arxiv.org/abs/2501.00001v1" rel="alternate" type="text/html"/>
        <arxiv:comment>Accepted at ICML 2026</arxiv:comment>
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2501.00002v1</id>
        <updated>2026-04-08T00:00:00Z</updated>
        <published>2026-04-08T00:00:00Z</published>
        <title>Paper B</title>
        <summary>Abstract B</summary>
        <link href="http://arxiv.org/abs/2501.00002v1" rel="alternate" type="text/html"/>
      </entry>
    </feed>"""

    source = SourceConfig(
        id="arxiv1",
        type="api",
        endpoint="https://export.arxiv.org/api/query",
        response_format="feed",
        comment_mode="with_comment",
        params={
            "search_query": "(cat:cs.AI) AND submittedDate:[202604070000 TO 202604080000]",
            "start": "0",
            "max_results": "50",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        },
    )
    client = FakeClient(FakeResponse(content=atom.encode("utf-8"), text=atom))
    fetcher = ApiFetcher()
    items = fetcher.fetch(source, client)  # type: ignore[arg-type]

    assert len(items) == 1
    assert items[0].title == "Paper A"
    assert items[0].extra.get("has_comment") is True
    assert "ICML 2026" in str(items[0].extra.get("comment"))
    assert "submittedDate:[202604070000 TO 202604080000]" in client.calls[0]["params"]["search_query"]


def test_api_fetcher_feed_filters_high_tier_comment_keywords():
    atom = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>http://arxiv.org/abs/2501.00001v1</id>
        <published>2026-04-08T00:00:00Z</published>
        <title>Paper A</title>
        <summary>Abstract A</summary>
        <link href="http://arxiv.org/abs/2501.00001v1" rel="alternate" type="text/html"/>
        <arxiv:comment>Accepted at Local Workshop 2026</arxiv:comment>
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2501.00002v1</id>
        <published>2026-04-08T00:00:00Z</published>
        <title>Paper B</title>
        <summary>Abstract B</summary>
        <link href="http://arxiv.org/abs/2501.00002v1" rel="alternate" type="text/html"/>
        <arxiv:comment>Accepted at NeurIPS 2026</arxiv:comment>
      </entry>
    </feed>"""

    source = SourceConfig(
        id="arxiv_tier",
        type="api",
        endpoint="https://export.arxiv.org/api/query",
        response_format="feed",
        comment_mode="with_comment",
        comment_tier_filter_enabled=True,
        comment_tier_keywords=["NeurIPS 2026", "ICML 2026"],
    )
    client = FakeClient(FakeResponse(content=atom.encode("utf-8"), text=atom))
    fetcher = ApiFetcher()
    items = fetcher.fetch(source, client)  # type: ignore[arg-type]

    assert len(items) == 1
    assert items[0].title == "Paper B"
    assert "NeurIPS 2026" in str(items[0].extra.get("comment"))


def test_api_fetcher_feed_filters_by_github_stars():
    atom = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>http://arxiv.org/abs/2501.00001v1</id>
        <published>2026-04-08T00:00:00Z</published>
        <title>Paper A</title>
        <summary>code: https://github.com/foo/bar</summary>
        <link href="http://arxiv.org/abs/2501.00001v1" rel="alternate" type="text/html"/>
        <arxiv:comment>Accepted at ICML 2026</arxiv:comment>
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2501.00002v1</id>
        <published>2026-04-08T00:00:00Z</published>
        <title>Paper B</title>
        <summary>code: https://github.com/foo/baz</summary>
        <link href="http://arxiv.org/abs/2501.00002v1" rel="alternate" type="text/html"/>
        <arxiv:comment>Accepted at ICML 2026</arxiv:comment>
      </entry>
    </feed>"""

    class MixedClient:
        def __init__(self):
            self.calls = []

        def get(self, url, params=None, headers=None, timeout=None):
            self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
            if "api.github.com/repos/foo/bar" in url:
                return FakeResponse(json_data={"stargazers_count": 500}, status_code=200)
            if "api.github.com/repos/foo/baz" in url:
                return FakeResponse(json_data={"stargazers_count": 10}, status_code=200)
            return FakeResponse(content=atom.encode("utf-8"), text=atom, status_code=200)

    source = SourceConfig(
        id="arxiv_github",
        type="api",
        endpoint="https://export.arxiv.org/api/query",
        response_format="feed",
        comment_mode="with_comment",
        comment_tier_filter_enabled=True,
        comment_tier_keywords=["ICML 2026"],
        github_filter_enabled=True,
        github_require_repo=True,
        github_stars_min=100,
    )
    client = MixedClient()
    fetcher = ApiFetcher()
    items = fetcher.fetch(source, client)  # type: ignore[arg-type]

    assert len(items) == 1
    assert items[0].title == "Paper A"
    assert items[0].extra.get("github_repo") == "foo/bar"
    assert items[0].extra.get("github_stars") == 500


def test_api_fetcher_quality_score_ranking_without_hard_star_gate():
    atom = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>http://arxiv.org/abs/2501.00001v1</id>
        <published>2026-04-08T00:00:00Z</published>
        <title>Top Paper</title>
        <summary>code: https://github.com/foo/top</summary>
        <link href="http://arxiv.org/abs/2501.00001v1" rel="alternate" type="text/html"/>
        <arxiv:comment>Accepted at NeurIPS 2026 Oral</arxiv:comment>
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2501.00002v1</id>
        <published>2026-04-08T00:00:00Z</published>
        <title>Normal Paper</title>
        <summary>code: https://github.com/foo/normal</summary>
        <link href="http://arxiv.org/abs/2501.00002v1" rel="alternate" type="text/html"/>
        <arxiv:comment>Accepted at Workshop 2026</arxiv:comment>
      </entry>
    </feed>"""

    class StarClient:
        def __init__(self):
            self.calls = []

        def get(self, url, params=None, headers=None, timeout=None):
            self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
            if "api.github.com/repos/foo/top" in url:
                return FakeResponse(json_data={"stargazers_count": 900}, status_code=200)
            if "api.github.com/repos/foo/normal" in url:
                return FakeResponse(json_data={"stargazers_count": 20}, status_code=200)
            return FakeResponse(content=atom.encode("utf-8"), text=atom, status_code=200)

    source = SourceConfig(
        id="arxiv_score",
        type="api",
        endpoint="https://export.arxiv.org/api/query",
        response_format="feed",
        comment_mode="with_comment",
        github_filter_enabled=True,
        github_require_repo=True,
        github_stars_min=0,
        quality_score_enabled=True,
        quality_score_min=0.0,
        quality_score_top_k=2,
        quality_weight_comment=0.35,
        quality_weight_venue=0.25,
        quality_weight_github=0.4,
        quality_weight_crossref=0.0,
        crossref_enabled=False,
    )
    client = StarClient()
    fetcher = ApiFetcher()
    items = fetcher.fetch(source, client)  # type: ignore[arg-type]

    assert len(items) == 2
    s0 = float(items[0].extra.get("quality_score") or 0)
    s1 = float(items[1].extra.get("quality_score") or 0)
    assert items[0].title == "Top Paper"
    assert s0 > s1
