"""Load and validate sources.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SourceConfig:
    source_id: str
    name: str
    country: str = "global"
    category: str = "other"
    type: str = "api"           # api | rss | html | dataset
    url: str = ""
    api_endpoint: str | None = None
    rss_url: str | None = None
    legal_level: str = "public"
    update_frequency: str = "daily"
    enabled: bool = False
    priority: str = "B"
    notes: str | None = None
    tier: str = "fast"          # fast | slow (cycle phasing: fast sources finish in <2s, slow take longer)
    extra: dict[str, Any] = field(default_factory=dict)

    def endpoint(self) -> str | None:
        return self.api_endpoint or self.rss_url


class Registry:
    """Source Registry. Phase 1 ships as an in-memory registry loaded from YAML."""

    def __init__(self, sources: list[SourceConfig]):
        self._by_id: dict[str, SourceConfig] = {s.source_id: s for s in sources}
        self._all = list(sources)

    def get(self, source_id: str) -> SourceConfig:
        if source_id not in self._by_id:
            raise KeyError(f"unknown source_id: {source_id}")
        return self._by_id[source_id]

    def all(self) -> list[SourceConfig]:
        return list(self._all)

    def enabled(self) -> list[SourceConfig]:
        return [s for s in self._all if s.enabled]

    def __len__(self) -> int:
        return len(self._all)

    def __contains__(self, source_id: object) -> bool:
        return source_id in self._by_id


def _coerce_source(raw: dict[str, Any]) -> SourceConfig:
    """Turn one YAML entry into a SourceConfig. Anything not in the dataclass
    fields goes into `extra` so we don't silently lose info."""
    field_names = {f for f in SourceConfig.__dataclass_fields__} - {"extra"}
    known = {k: raw[k] for k in raw if k in field_names}
    extra = {k: v for k, v in raw.items() if k not in field_names}
    return SourceConfig(**known, extra=extra)


def load_registry(path: str | Path) -> Registry:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"sources config not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    sources_raw = data.get("sources") or []
    sources = [_coerce_source(s) for s in sources_raw]
    return Registry(sources)