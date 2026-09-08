"""GDELT 2.0 DOC collector.

API: https://api.gdeltproject.org/api/v2/doc/doc
Examples:
  ?query=AI&mode=artlist&format=json&maxrecords=50
  ?query=AI&mode=tonechart&format=json
"""
from __future__ import annotations

from urllib.parse import urlencode

from ..config import SourceConfig
from ..models import RawItem, normalize_dt
from .base import BaseCollector, CollectorError, HttpFetcher, register


@register
class GDELTCollector(BaseCollector):
    source_id = "gdelt"
    description = "GDELT 2.0 global events"

    DEFAULT_QUERY = "(AI OR artificial intelligence OR machine learning OR OpenAI OR Anthropic OR Nvidia)"
    MAX_RECORDS = 50

    def __init__(self, fetcher: HttpFetcher | None = None, query: str | None = None,
                 max_records: int = MAX_RECORDS, sources_lang: str = "en"):
        super().__init__(fetcher)
        self.query = query or self.DEFAULT_QUERY
        self.max_records = max_records
        self.sources_lang = sources_lang

    def collect(self, source: SourceConfig) -> list[RawItem]:
        endpoint = source.api_endpoint or source.endpoint()
        if not endpoint:
            raise CollectorError(f"source {source.source_id} missing api_endpoint")

        params = {
            "query": self.query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": str(self.max_records),
            "sourcelang": self.sources_lang,
            "sort": "datedesc",
        }
        url = f"{endpoint.rstrip('/')}?{urlencode(params)}"
        try:
            data = self.fetcher.fetch_json(url)
        except CollectorError as e:
            raise CollectorError(f"GDELT fetch failed: {e}") from e

        articles = (data or {}).get("articles") or []
        items: list[RawItem] = []
        for i, a in enumerate(articles):
            title = a.get("title") or ""
            url_ = a.get("url") or ""
            if not title or not url_:
                continue
            seendate = a.get("seendate")  # GDELT format YYYYMMDDTHHMMSSZ
            items.append(self._make(
                source_id=source.source_id,
                external_id=a.get("url") or f"gdelt-{i}",
                url=url_,
                title=title,
                content="",
                published_at=normalize_dt(seendate),
                domain=a.get("domain"),
                language=a.get("language"),
                source_common_name=a.get("sourceCommonName"),
                tone=a.get("tone"),
            ))
        return items