"""GitHub Releases collector.

API: https://api.github.com/repos/{owner}/{repo}/releases
Auth: optional token via GITHUB_TOKEN env (60 → 5000 req/h vs 60).

Default watchlist is a small set of high-signal AI/agent repos. Edit
or pass your own list via the source config's `extra.watchlist` /
`metadata` JSON.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from ..config import SourceConfig
from ..models import RawItem, normalize_dt
from .base import BaseCollector, CollectorError, register

DEFAULT_WATCHLIST = [
    ("openai", "openai-python"),
    ("anthropics", "anthropic-sdk-python"),
    ("langchain-ai", "langchain"),
    ("langchain-ai", "langgraph"),
    ("openai", "swarm"),
    ("anthropics", "claude-code"),
    ("browser-use", "browser-use"),
    ("All-Hands-AI", "OpenHands"),
    ("crewAIInc", "crewAI"),
    ("expo", "expo"),
    ("vercel", "ai"),
]


@register
class GitHubReleasesCollector(BaseCollector):
    source_id = "github_releases"
    description = "GitHub Releases for a curated AI/agent watchlist"

    def __init__(self, *args, watchlist: list[tuple[str, str]] | None = None,
                 per_repo: int = 5, **kwargs):
        super().__init__(*args, **kwargs)
        self.watchlist = watchlist or DEFAULT_WATCHLIST
        self.per_repo = per_repo

    def collect(self, source: SourceConfig) -> list[RawItem]:
        from ..config import SourceConfig as SC  # noqa: F401  (for type hints)
        # Optional token from env
        import os
        token = os.environ.get("GITHUB_TOKEN")
        auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

        items: list[RawItem] = []
        for owner, repo in self.watchlist:
            url = f"https://api.github.com/repos/{owner}/{repo}/releases"
            try:
                data = self.fetcher.fetch_json(url, headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    **auth_headers,
                })
            except CollectorError as e:
                # one bad repo shouldn't sink the whole source
                items.append(RawItem(
                    source_id=source.source_id,
                    external_id=f"{owner}/{repo}",
                    url=url,
                    title=f"[fetch error] {owner}/{repo}",
                    metadata={"fetch_error": str(e)},
                ))
                continue
            if not isinstance(data, list):
                continue
            for rel in data[: self.per_repo]:
                tag = rel.get("tag_name") or ""
                name = rel.get("name") or tag or "(no name)"
                html_url = rel.get("html_url") or f"https://github.com/{owner}/{repo}/releases"
                published = normalize_dt(rel.get("published_at") or rel.get("created_at"))
                body = (rel.get("body") or "").strip()[:1500]
                external_id = f"{owner}/{repo}@{rel.get('id', tag)}"
                items.append(self._make(
                    source_id=source.source_id,
                    external_id=external_id,
                    url=html_url,
                    title=f"{owner}/{repo}: {name}",
                    content=body,
                    published_at=published,
                    tag=tag,
                    prerelease=rel.get("prerelease", False),
                    author=(rel.get("author") or {}).get("login"),
                ))
        return items