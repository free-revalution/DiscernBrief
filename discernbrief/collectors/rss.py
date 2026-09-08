"""Generic RSS / Atom collector.

Handles both RSS 2.0 (`<rss><channel><item>`) and Atom
(`<feed><entry>`). Uses stdlib xml.etree; no extra dependencies.

Each registered subclass only needs `source_id` and optionally `category`.
The URL is read from the SourceConfig (api_endpoint or rss_url).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from ..config import SourceConfig
from ..models import RawItem, normalize_dt
from .base import BaseCollector, HttpFetcher, register

ATOM = "{http://www.w3.org/2005/Atom}"
CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}"
DC = "{http://purl.org/dc/elements/1.1/}"


def _text(el, default: str = "") -> str:
    if el is None or el.text is None:
        return default
    return " ".join(el.text.split())


def _atom_link_href(entry) -> str | None:
    """Atom <link> can be a child element with href attribute, not text."""
    for link in entry.findall(f"{ATOM}link"):
        href = link.get("href")
        rel = link.get("rel", "alternate")
        if href and rel in ("alternate", ""):
            return href.strip()
    return None


def _parse_pub_date(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        dt = parsedate_to_datetime(text)
        return normalize_dt(dt)
    except (TypeError, ValueError):
        return normalize_dt(text)


def parse_rss_or_atom(body: str, source_id: str, source_url: str,
                      limit: int = 30) -> list[RawItem]:
    """Parse a feed body (RSS 2.0 or Atom) into RawItems."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        from .base import CollectorError
        raise CollectorError(f"{source_id}: invalid XML: {e}") from e

    items: list[RawItem] = []

    if root.tag == f"{ATOM}feed":
        # Atom
        for entry in root.findall(f"{ATOM}entry"):
            title = _text(entry.find(f"{ATOM}title"))
            url_ = _atom_link_href(entry) or _text(entry.find(f"{ATOM}id"))
            if not title or not url_:
                continue
            external_id = url_
            summary = _text(entry.find(f"{ATOM}summary"))
            content_el = entry.find(f"{ATOM}content")
            if content_el is not None and content_el.text:
                summary = summary or " ".join(content_el.text.split()[:600])
            published = _parse_pub_date(_text(entry.find(f"{ATOM}published"))) or \
                       _parse_pub_date(_text(entry.find(f"{ATOM}updated")))
            author_el = entry.find(f"{ATOM}author/{ATOM}name")
            author = _text(author_el) or None
            items.append(RawItem(
                source_id=source_id,
                external_id=external_id,
                url=url_,
                title=title,
                content=summary,
                published_at=published,
                metadata={"feed_url": source_url, "author": author} if author else {"feed_url": source_url},
            ))
            if len(items) >= limit:
                break
        return items

    # RSS 2.0 (or RDF); channel/item
    channel = root.find("channel") if root.tag == "rss" else root
    if channel is None:
        from .base import CollectorError
        raise CollectorError(f"{source_id}: no <channel> element")

    for item in channel.findall("item"):
        title = _text(item.find("title"))
        url_ = _text(item.find("link"))
        if not title or not url_:
            continue
        guid = _text(item.find("guid")) or url_
        desc = _text(item.find("description"))
        # Some feeds put HTML in <content:encoded>
        content_el = item.find(f"{CONTENT_NS}encoded")
        if content_el is not None and content_el.text:
            desc = " ".join(content_el.text.split()[:600])
        pub = _parse_pub_date(_text(item.find("pubDate"))) or \
             _parse_pub_date(_text(item.find(f"{DC}date")))
        creator = _text(item.find(f"{DC}creator")) or None
        items.append(RawItem(
            source_id=source_id,
            external_id=guid,
            url=url_,
            title=title,
            content=desc,
            published_at=pub,
            metadata={"feed_url": source_url, "author": creator} if creator else {"feed_url": source_url},
        ))
        if len(items) >= limit:
            break
    return items


class RSSFeedCollector(BaseCollector):
    """Single RSS/Atom collector reused by every RSS source in the registry.

    Subclasses only need to set `source_id` — no source-specific logic.
    """
    source_id = ""  # overridden by subclasses
    description = "Generic RSS/Atom feed collector"
    limit = 30

    def collect(self, source: SourceConfig) -> list[RawItem]:
        url = source.rss_url or source.api_endpoint or source.url
        if not url:
            from .base import CollectorError
            raise CollectorError(f"{source.source_id}: no RSS URL configured")
        body = self.fetcher.fetch_text(url)
        return parse_rss_or_atom(body, source_id=source.source_id,
                                 source_url=url, limit=self.limit)


# Concrete registrations — one class per source so each gets its own
# source_id for the registry. No source-specific logic needed.

@register
class OpenAIBlogCollector(RSSFeedCollector):
    source_id = "openai_blog"


@register
class GoogleAIBlogCollector(RSSFeedCollector):
    source_id = "google_ai_blog"


@register
class TechCrunchCollector(RSSFeedCollector):
    source_id = "techcrunch"


@register
class TheVergeCollector(RSSFeedCollector):
    source_id = "theverge"


@register
class QbitaiCollector(RSSFeedCollector):
    source_id = "qbitai"


@register
class Kr36Collector(RSSFeedCollector):
    source_id = "kr36"


@register
class SspaiCollector(RSSFeedCollector):
    source_id = "sspai"


@register
class JiqizhixinCollector(RSSFeedCollector):
    source_id = "jiqizhixin"


@register
class SyncedCollector(RSSFeedCollector):
    source_id = "synced"


@register
class GoogleNewsCollector(RSSFeedCollector):
    source_id = "google_news"


@register
class V2EXCollector(RSSFeedCollector):
    source_id = "v2ex"


@register
class GeekparkCollector(RSSFeedCollector):
    source_id = "geekpark"


@register
class HackerNewsBestCollector(RSSFeedCollector):
    """HN best-stories feed via the public hnrss.org mirror."""
    source_id = "hackernews_best"
    limit = 25


@register
class LobstersCollector(RSSFeedCollector):
    source_id = "lobsters"


@register
class LWNCollector(RSSFeedCollector):
    source_id = "lwn"


@register
class RedditRSSCollector(RSSFeedCollector):
    """Multi-subreddit RSS fan-in. Subs are listed in source's metadata_json
    via the `subreddits` list, or defaults to a high-signal AI/agent set."""
    source_id = "reddit_rss"

    DEFAULT_SUBS = [
        "MachineLearning", "artificial", "LocalLLaMA",
        "ClaudeAI", "OpenAI", "startups", "Entrepreneur",
    ]

    def collect(self, source: SourceConfig) -> list[RawItem]:
        subs = list(self.DEFAULT_SUBS)
        # SourceConfig puts anything-not-a-known-field into `extra`
        extra = source.extra or {}
        subs = extra.get("subreddits") or subs
        limit_per = max(5, self.limit // max(1, len(subs)))
        out: list[RawItem] = []
        for sub in subs:
            url = f"https://www.reddit.com/r/{sub}/.rss"
            try:
                body = self.fetcher.fetch_text(url)
                out.extend(parse_rss_or_atom(body, source_id=source.source_id,
                                            source_url=url, limit=limit_per))
            except Exception:
                continue
        return out