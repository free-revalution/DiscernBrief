"""Filter pipeline: takes raw_items → keeps high-value → produces Signals.

The LLM layer is abstracted. ManualLlm is the default for early dev:
it prints a prompt to stdout / file and expects JSON on stdin / a
follow-up `ingest-signals` call.

Spec §24 funnel: 10000 raw → 1000 → 300 → 50 → 10-30 signals
For Phase 5 we operate on whatever batch we already have in raw_items.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from typing import Iterable

from ..db import Database
from ..models import RawItem
from .schema import CATEGORIES, IMPORTANCE_LEVELS, Signal


# ── prompt builders ──────────────────────────────────────────────────────

def items_for_prompt(items: list[dict]) -> str:
    """Format items as a JSON block for the LLM prompt."""
    compact = []
    for it in items:
        compact.append({
            "raw_id": it["id"],
            "source": it["source_id"],
            "title": it["title"],
            "snippet": (it.get("content") or "")[:400],
            "url": it["url"],
            "published_at": it.get("published_at"),
        })
    return json.dumps(compact, ensure_ascii=False, indent=2)


def build_judgment_prompt(items: list[dict]) -> str:
    items_block = items_for_prompt(items)
    return f"""You are the filter stage of an "AI Opportunity Radar".
Your job: read {len(items)} news items and decide which are worth
turning into a *commercial signal* (something that could matter for
business, founders, product, sales, content, investment decisions).

For each item, output exactly one judgment object:

{{
  "raw_id": <int from input>,
  "keep": <true|false>,
  "category": <one of: {', '.join(CATEGORIES)}>,
  "importance": <one of: {', '.join(IMPORTANCE_LEVELS)}>,
  "summary": "<one sentence, ≤30 words, what happened>",
  "why_it_matters": "<one sentence, ≤30 words, why this is meaningful>",
  "business_angle": "<one sentence, ≤30 words, who should act and how>",
  "confidence": <0.0-1.0, your certainty the judgment is right>
}}

Rules:
- drop items that are pure noise: tutorial reposts, library updates
  with no business impact, generic AI hype, low-information listicles
- if importance is LOW, you may leave business_angle empty
- output ONE JSON object with key "judgments" containing the array

Items:
{items_block}

Respond with ONLY the JSON, no prose before or after.
"""


# ── response parsing ─────────────────────────────────────────────────────

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def parse_judgments(text: str) -> list[dict]:
    """Parse the LLM's JSON response, tolerating ```json fences."""
    if not text or not text.strip():
        return []
    # Try direct parse first
    candidates = [text.strip()]
    # Strip fences
    m = _JSON_FENCE.search(text)
    if m:
        candidates.append(m.group(1).strip())
    # Take the first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start:end + 1])

    for c in candidates:
        try:
            data = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "judgments" in data and isinstance(data["judgments"], list):
            return data["judgments"]
        if isinstance(data, list):
            return data
    return []


# ── pipeline ─────────────────────────────────────────────────────────────

class FilterPipeline:
    """Orchestrates: fetch raw_items → build prompt → call LLM → write signals."""

    def __init__(self, db: Database, llm):
        self.db = db
        self.llm = llm

    def fetch_batch(self, limit: int = 20, source_id: str | None = None,
                    only_unprocessed: bool = True) -> list[dict]:
        """Fetch raw_items as plain dicts, ordered newest-first."""
        where: list[str] = []
        params: list = []
        if source_id:
            where.append("source_id = ?")
            params.append(source_id)
        if only_unprocessed:
            where.append("id NOT IN (SELECT raw_id FROM signal_raw_items)")
        sql = (
            "SELECT id, source_id, external_id, url, title, content, "
            "published_at, collected_at, content_hash, metadata_json "
            "FROM raw_items"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def run(self, limit: int = 20, source_id: str | None = None) -> dict:
        items = self.fetch_batch(limit=limit, source_id=source_id)
        if not items:
            return {"fetched": 0, "kept": 0, "dropped": 0, "signals_written": 0}

        prompt = build_judgment_prompt(items)
        response = self.llm.complete(prompt)
        judgments = parse_judgments(response)

        by_id = {it["id"]: it for it in items}
        kept, dropped = [], []
        signals: list[Signal] = []
        for j in judgments:
            raw_id = j.get("raw_id")
            if raw_id not in by_id:
                continue
            if not j.get("keep", False):
                dropped.append(raw_id)
                continue
            it = by_id[raw_id]
            sig = Signal(
                raw_item_ids=[raw_id],
                title=(j.get("summary") or it["title"])[:200],
                summary=(j.get("summary") or ""),
                why_it_matters=(j.get("why_it_matters") or ""),
                business_angle=(j.get("business_angle") or ""),
                category=j.get("category", "其他"),
                importance=j.get("importance", "MEDIUM"),
                source_urls=[it["url"]],
                published_at=it.get("published_at"),
                confidence=float(j.get("confidence", 0.5)),
                metadata={"source_id": it["source_id"], "judged_via": "filter_v1"},
            )
            errs = sig.validate()
            if errs:
                # salvage: coerce invalid category/importance, keep signal
                if sig.category not in CATEGORIES:
                    sig.category = "其他"
                if sig.importance not in IMPORTANCE_LEVELS:
                    sig.importance = "MEDIUM"
                sig.confidence = max(0.0, min(1.0, sig.confidence))
            signals.append(sig)
            kept.append(raw_id)

        written = 0
        for sig in signals:
            if self.db.insert_signal(sig):
                written += 1

        return {
            "fetched": len(items),
            "judged": len(judgments),
            "kept": len(kept),
            "dropped": len(dropped),
            "signals_written": written,
        }