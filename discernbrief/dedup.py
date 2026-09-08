"""Dedup helpers. Spec §4.

Two passes:
  1. URL exact-match dedup (handled by SQLite UNIQUE on content_hash).
  2. Within-batch title-similarity dedup (cheap, ~O(n) using difflib).

True near-duplicate detection (MinHash, simhash) is Phase 4 polish; the
title heuristic catches the common case of two outlets posting the same
press release.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Iterable

from .models import RawItem

SIMILARITY_THRESHOLD = 0.85


def _normalize_title(s: str) -> str:
    return " ".join(s.lower().split())


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize_title(a), _normalize_title(b)).ratio()


def dedup_by_title(items: Iterable[RawItem], threshold: float = SIMILARITY_THRESHOLD) -> list[RawItem]:
    """Drop later items whose title is too similar to an earlier one.

    The first occurrence wins; later near-duplicates are removed.
    """
    kept: list[RawItem] = []
    for item in items:
        dup_of: int | None = None
        for j, prior in enumerate(kept):
            if _ratio(item.title, prior.title) >= threshold:
                dup_of = j
                break
        if dup_of is None:
            kept.append(item)
        else:
            # enrich the surviving record so we don't lose context
            prior = kept[dup_of]
            if not prior.content and item.content:
                prior.content = item.content
            prior.metadata.setdefault("also_seen_on", [])
            prior.metadata["also_seen_on"].append({
                "source_id": item.source_id,
                "url": item.url,
            })
    return kept