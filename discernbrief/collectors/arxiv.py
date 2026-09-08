"""arXiv collector using the public arXiv API.

API: https://export.arxiv.org/api/query?search_query=...&start=0&max_results=20
Returns Atom XML. We parse with stdlib xml.etree.

Default query targets cs.AI / cs.CL / cs.LG categories, sorted by
submission date descending. Each result has a stable id (the URL suffix).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from ..config import SourceConfig
from ..models import RawItem, normalize_dt
from .base import BaseCollector, CollectorError, HttpFetcher, register

ATOM = "{http://www.w3.org/2005/Atom}"


@register
class ArxivCollector(BaseCollector):
    source_id = "arxiv"
    description = "arXiv preprint server (Atom API)"

    DEFAULT_QUERY = "cat:cs.AI OR cat:cs.CL OR cat:cs.LG"
    DEFAULT_MAX = 25

    def __init__(self, fetcher: HttpFetcher | None = None, query: str | None = None,
                 max_results: int = DEFAULT_MAX, sort_by: str = "submittedDate",
                 sort_order: str = "descending"):
        super().__init__(fetcher)
        self.query = query or self.DEFAULT_QUERY
        self.max_results = max_results
        self.sort_by = sort_by
        self.sort_order = sort_order

    def collect(self, source: SourceConfig) -> list[RawItem]:
        endpoint = source.api_endpoint or source.endpoint()
        if not endpoint:
            raise CollectorError(f"source {source.source_id} missing api_endpoint")
        params = {
            "search_query": self.query,
            "start": "0",
            "max_results": str(self.max_results),
            "sortBy": self.sort_by,
            "sortOrder": self.sort_order,
        }
        url = f"{endpoint.rstrip('/')}?{urlencode(params)}"
        body = self.fetcher.fetch_text(url, headers={"Accept": "application/atom+xml"})
        try:
            root = ET.fromstring(body)
        except ET.ParseError as e:
            raise CollectorError(f"arXiv returned non-XML body: {e}") from e

        items: list[RawItem] = []
        for entry in root.findall(f"{ATOM}entry"):
            title_el = entry.find(f"{ATOM}title")
            id_el = entry.find(f"{ATOM}id")
            published_el = entry.find(f"{ATOM}published")
            updated_el = entry.find(f"{ATOM}updated")
            summary_el = entry.find(f"{ATOM}summary")
            author_els = entry.findall(f"{ATOM}author/{ATOM}name")

            title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
            url_ = (id_el.text or "").strip() if id_el is not None else ""
            if not title or not url_:
                continue

            external_id = url_.rsplit("/", 1)[-1] or url_
            summary = (summary_el.text or "").strip() if summary_el is not None else ""
            authors = [n.text.strip() for n in author_els if n.text]
            published = normalize_dt(published_el.text if published_el is not None else None)

            items.append(self._make(
                source_id=source.source_id,
                external_id=external_id,
                url=url_,
                title=title,
                content=summary,
                published_at=published,
                authors=authors,
                updated_at=normalize_dt(updated_el.text if updated_el is not None else None),
            ))
        return items