"""Domain models. Mirrors the schema in SPEC § §23."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_dt(value: Any) -> datetime | None:
    """Best-effort datetime parser. Accepts ISO strings, epoch seconds, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        s = value.strip()
        # GDELT uses formats like 20260101T120000Z
        if "T" in s and len(s) >= 15 and s.endswith("Z"):
            try:
                return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        # Python 3.10+ accepts trailing Z; on 3.9 we replace it
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


@dataclass
class RawItem:
    source_id: str
    external_id: str
    url: str
    title: str
    content: str = ""
    published_at: datetime | None = None
    collected_at: datetime = field(default_factory=utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def content_hash(self) -> str:
        """Stable hash for dedup. Uses url+title — change means new content."""
        h = hashlib.sha256()
        h.update(self.url.strip().lower().encode("utf-8"))
        h.update(b"\x00")
        h.update(self.title.strip().lower().encode("utf-8"))
        return h.hexdigest()

    def to_db_row(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "external_id": self.external_id,
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "collected_at": self.collected_at.isoformat(),
            "content_hash": self.content_hash(),
            "metadata_json": json.dumps(self.metadata, ensure_ascii=False, default=str),
        }

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.published_at:
            d["published_at"] = self.published_at.isoformat()
        d["collected_at"] = self.collected_at.isoformat()
        d["content_hash"] = self.content_hash()
        return d


@dataclass
class RunResult:
    started_at: datetime = field(default_factory=utcnow)
    finished_at: datetime | None = None
    source_count: int = 0
    raw_item_count: int = 0
    signal_count: int = 0
    status: str = "running"
    error: str | None = None

    def finish(self, status: str = "ok", error: str | None = None) -> None:
        self.finished_at = utcnow()
        self.status = status
        self.error = error