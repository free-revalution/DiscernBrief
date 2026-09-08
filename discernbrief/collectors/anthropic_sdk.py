"""Anthropic SDK GitHub Releases collector (Atom feed)."""
from __future__ import annotations

from ..config import SourceConfig
from .base import BaseCollector, register
from .rss import parse_rss_or_atom


@register
class AnthropicSDKCollector(BaseCollector):
    source_id = "anthropic_sdk"
    description = "Anthropic Python SDK releases via GitHub Atom feed"

    limit = 10

    def collect(self, source: SourceConfig) -> list:
        url = source.rss_url or source.api_endpoint or source.url
        if not url:
            from .base import CollectorError
            raise CollectorError(f"{source.source_id}: no Atom URL configured")
        body = self.fetcher.fetch_text(url)
        return parse_rss_or_atom(body, source_id=source.source_id,
                                 source_url=url, limit=self.limit)