"""Normalization helpers. Spec §3."""
from __future__ import annotations

import re
from typing import Iterable

from .models import RawItem

_WS = re.compile(r"\s+")
_HTML_TAG = re.compile(r"<[^>]+>")
_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref"}


def clean_title(title: str) -> str:
    if not title:
        return ""
    t = _HTML_TAG.sub("", title)
    t = _WS.sub(" ", t).strip()
    return t


def clean_url(url: str) -> str:
    if not url:
        return ""
    from urllib.parse import urlparse, urlunparse, parse_qsl
    try:
        u = urlparse(url)
    except ValueError:
        return url
    # strip common tracking params
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if k not in _TRACKING_PARAMS]
    return urlunparse((u.scheme, u.netloc.lower(), u.path, u.params,
                       "&".join(f"{k}={v}" for k, v in q), ""))


def normalize(item: RawItem) -> RawItem:
    return RawItem(
        source_id=item.source_id,
        external_id=item.external_id,
        url=clean_url(item.url),
        title=clean_title(item.title),
        content=item.content or "",
        published_at=item.published_at,
        collected_at=item.collected_at,
        metadata=dict(item.metadata),
    )


def normalize_many(items: Iterable[RawItem]) -> list[RawItem]:
    return [normalize(i) for i in items]