"""Hacker News collector via the public Firebase API.

Endpoints used:
  GET /v0/topstories.json         → list of story ids (top stories)
  GET /v0/beststories.json        → best stories
  GET /v0/newstories.json         → newest
  GET /v0/item/<id>.json          → single item
"""
from __future__ import annotations

from typing import Literal

from ..config import SourceConfig
from ..models import RawItem, normalize_dt
from .base import BaseCollector, CollectorError, HttpFetcher, register

FeedType = Literal["top", "best", "new"]


@register
class HackerNewsCollector(BaseCollector):
    source_id = "hackernews"
    description = "Hacker News via Firebase API"

    def __init__(self, fetcher: HttpFetcher | None = None, feed: FeedType = "top",
                 max_items: int = 30):
        super().__init__(fetcher)
        self.feed = feed
        self.max_items = max_items

    def _ids_url(self, api_endpoint: str) -> str:
        return f"{api_endpoint.rstrip('/')}/{self.feed}stories.json"

    def collect(self, source: SourceConfig) -> list[RawItem]:
        endpoint = source.api_endpoint or source.endpoint()
        if not endpoint:
            raise CollectorError(f"source {source.source_id} missing api_endpoint")

        ids = self.fetcher.fetch_json(self._ids_url(endpoint))
        if not isinstance(ids, list):
            raise CollectorError(f"unexpected HN ids payload: {type(ids)}")
        ids = ids[: self.max_items]

        items: list[RawItem] = []
        for story_id in ids:
            try:
                raw = self.fetcher.fetch_json(f"{endpoint.rstrip('/')}/item/{story_id}.json")
            except CollectorError as e:
                # one bad item shouldn't sink the whole feed
                items.append(RawItem(
                    source_id=source.source_id,
                    external_id=str(story_id),
                    url="",
                    title="",
                    metadata={"fetch_error": str(e)},
                ))
                continue
            if not raw:
                continue
            url = raw.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
            title = raw.get("title") or ""
            if not title:
                continue
            text = raw.get("text") or ""
            items.append(self._make(
                source_id=source.source_id,
                external_id=str(story_id),
                url=url,
                title=title,
                content=text,
                published_at=normalize_dt(raw.get("time")),
                score=raw.get("score"),
                by=raw.get("by"),
                descendants=raw.get("descendants"),
                type=raw.get("type"),
            ))
        return items