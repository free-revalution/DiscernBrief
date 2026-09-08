"""Base Collector interface.

A Collector turns one configured SourceConfig into a list of RawItem.
It should not write to the database, not call AI, not dedup — that's the
pipeline's job. Pure transform.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from ..config import SourceConfig
from ..models import RawItem

REGISTRY: dict[str, "BaseCollector"] = {}


def register(cls: type["BaseCollector"]) -> type["BaseCollector"]:
    REGISTRY[cls.source_id] = cls()
    return cls


class CollectorError(RuntimeError):
    pass


class HttpFetcher:
    """Tiny urllib wrapper. Adds UA, retries on 5xx, returns decoded body."""

    DEFAULT_UA = "DiscernBrief/0.1 (+https://example.local)"
    DEFAULT_TIMEOUT = 20

    def __init__(self, ua: str | None = None, timeout: int | None = None):
        self.ua = ua or self.DEFAULT_UA
        self.timeout = timeout or self.DEFAULT_TIMEOUT

    def fetch_text(self, url: str, params: dict[str, Any] | None = None,
                   headers: dict[str, str] | None = None,
                   max_retries: int = 2,
                   sleep_between: float = 0.6) -> str:
        if params:
            from urllib.parse import urlencode
            url = f"{url}?{urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "User-Agent": self.ua,
            "Accept": "application/json, application/xml, text/xml;q=0.9, */*;q=0.5",
            **(headers or {}),
        })
        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return resp.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as e:
                if e.code < 500 or attempt == max_retries:
                    raise CollectorError(f"HTTP {e.code} on {url}: {e.reason}") from e
                last_err = e
            except urllib.error.URLError as e:
                last_err = e
            time.sleep(sleep_between * (attempt + 1))
        raise CollectorError(f"fetch failed after retries: {url}: {last_err}")

    def fetch_json(self, url: str, params: dict[str, Any] | None = None,
                   headers: dict[str, str] | None = None) -> Any:
        body = self.fetch_text(url, params=params,
                               headers={"Accept": "application/json", **(headers or {})})
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise CollectorError(f"non-JSON body from {url}: {e}") from e


class CurlFetcher:
    """Subprocess curl wrapper. Used for sites where Python's urllib hits SSL
    issues that libcurl handles better (commonly CN CDNs and older TLS)."""

    DEFAULT_UA = "DiscernBrief/0.1 (+https://example.local)"
    DEFAULT_TIMEOUT = 20

    def __init__(self, ua: str | None = None, timeout: int | None = None):
        self.ua = ua or self.DEFAULT_UA
        self.timeout = timeout or self.DEFAULT_TIMEOUT

    def _curl(self, url: str, params: dict | None, headers: dict | None) -> str:
        import subprocess
        from urllib.parse import urlencode
        cmd = [
            "curl", "-sLf",
            "--max-time", str(self.timeout),
            "--retry", "2", "--retry-delay", "1",
            "-A", self.ua,
            "-H", "Accept: application/json, application/xml, text/xml;q=0.9, */*;q=0.5",
        ]
        for k, v in (headers or {}).items():
            cmd.extend(["-H", f"{k}: {v}"])
        if params:
            url = f"{url}?{urlencode(params)}"
        cmd.append(url)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout + 5)
        except subprocess.TimeoutExpired as e:
            raise CollectorError(f"curl timeout on {url}") from e
        if r.returncode != 0:
            raise CollectorError(f"curl failed on {url} (rc={r.returncode}): {(r.stderr or '')[:200]}")
        return r.stdout

    def fetch_text(self, url: str, params: dict[str, Any] | None = None,
                   headers: dict[str, str] | None = None,
                   max_retries: int = 1,
                   sleep_between: float = 0.3) -> str:
        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return self._curl(url, params, headers)
            except CollectorError as e:
                last_err = e
            time.sleep(sleep_between * (attempt + 1))
        raise CollectorError(f"curl fetch failed after retries: {url}: {last_err}")

    def fetch_json(self, url: str, params: dict[str, Any] | None = None,
                   headers: dict[str, str] | None = None) -> Any:
        body = self.fetch_text(url, params=params,
                               headers={"Accept": "application/json", **(headers or {})})
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise CollectorError(f"non-JSON body from {url}: {e}") from e


class FallbackFetcher:
    """Try urllib first; on CollectorError fall back to curl.

    Chinese CDNs in particular accept libcurl connections while rejecting
    Python's default SSL stack (EOF in violation of protocol). With this as
    the default, no per-source config is needed.
    """

    def __init__(self, ua: str | None = None, timeout: int | None = None):
        self.urllib = HttpFetcher(ua, timeout)
        self.curl = CurlFetcher(ua, timeout)

    def fetch_text(self, url: str, params: dict[str, Any] | None = None,
                   headers: dict[str, str] | None = None,
                   max_retries: int = 1,
                   sleep_between: float = 0.3) -> str:
        try:
            return self.urllib.fetch_text(url, params, headers, max_retries, sleep_between)
        except CollectorError:
            return self.curl.fetch_text(url, params, headers, max_retries, sleep_between)

    def fetch_json(self, url: str, params: dict[str, Any] | None = None,
                   headers: dict[str, str] | None = None) -> Any:
        body = self.fetch_text(url, params=params,
                               headers={"Accept": "application/json", **(headers or {})})
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise CollectorError(f"non-JSON body from {url}: {e}") from e


class BaseCollector(ABC):
    source_id: ClassVar[str] = ""
    description: ClassVar[str] = ""

    def __init__(self, fetcher=None):
        # Default to FallbackFetcher so SSL-restricted hosts (commonly CN CDNs)
        # automatically fall back to libcurl when Python's urllib hits EOF.
        self.fetcher = fetcher or FallbackFetcher()

    @abstractmethod
    def collect(self, source: SourceConfig) -> list[RawItem]:
        ...

    @staticmethod
    def _make(source_id: str, external_id: str, url: str, title: str,
              content: str = "", published_at=None, **metadata) -> RawItem:
        return RawItem(
            source_id=source_id,
            external_id=str(external_id),
            url=url,
            title=title,
            content=content,
            published_at=published_at,
            metadata=metadata,
        )