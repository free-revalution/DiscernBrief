"""CLI entry point.

Usage:
    python -m discernbrief.cli ingest [--source hackernews] [--dry-run]
    python -m discernbrief.cli sources
    python -m discernbrief.cli status
    python -m discernbrief.cli recent [--limit 20]

Phase 5+ will add: `analyze`, `report`.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from .collectors import all_collectors
from .config import load_registry
from .db import Database
from .dedup import dedup_by_title
from .models import RunResult
from .normalize import normalize_many

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "sources.yaml"
DEFAULT_DB = REPO_ROOT / "data" / "discernbrief.db"


def cmd_sources(args, registry, db) -> int:
    rows = db.all_sources()
    enabled_ids = {s.source_id for s in registry.enabled()}
    print(f"{'source_id':<22} {'priority':<5} {'enabled':<8} {'type':<6}  name")
    print("-" * 90)
    for r in rows:
        en = "yes" if r["source_id"] in enabled_ids else "no"
        print(f"{r['source_id']:<22} {r['priority']:<5} {en:<8} {r['type']:<6}  {r['name']}")
    print(f"\nTotal: {len(rows)} registered, {len(enabled_ids)} enabled.")
    return 0


def cmd_status(args, registry, db) -> int:
    runs = db.list_runs(limit=5)
    total_items = db.count_raw_items()
    enabled = len(registry.enabled())
    print(f"DB:           {db.path}")
    print(f"raw_items:    {total_items}")
    print(f"enabled:      {enabled} / {len(registry)} sources")
    print(f"recent runs:")
    for r in runs:
        dur = ""
        if r.get("finished_at") and r.get("started_at"):
            try:
                from datetime import datetime
                a = datetime.fromisoformat(r["started_at"])
                b = datetime.fromisoformat(r["finished_at"])
                dur = f" ({(b - a).total_seconds():.1f}s)"
            except Exception:
                pass
        err = f" ERROR={r['error']}" if r.get("error") else ""
        print(f"  #{r['id']:<3} {r['status']:<10} sources={r['source_count']:<3} "
              f"items={r['raw_item_count']:<5}{dur}{err}")
    return 0


def cmd_recent(args, registry, db) -> int:
    rows = db.recent_raw_items(limit=args.limit)
    for r in rows:
        pub = r.get("published_at") or "—"
        print(f"[{r['source_id']:<11}] {pub[:19]:<19}  {r['title']}")
        print(f"    {r['url']}")
    return 0


def cmd_ingest(args, registry, db) -> int:
    sources = registry.enabled()
    if args.source:
        wanted = {s.strip() for s in args.source.split(",") if s.strip()}
        sources = [s for s in sources if s.source_id in wanted]
        if not sources:
            print(f"no enabled sources match {args.source!r}", file=sys.stderr)
            return 2

    collectors = all_collectors()
    by_id = {c.source_id: c for c in collectors}

    run = RunResult()
    run_id = db.start_run()
    total_collected = 0
    total_inserted = 0
    failures = []

    print(f"=== ingest run #{run_id} ===")
    for source in sources:
        collector = by_id.get(source.source_id)
        if collector is None:
            print(f"[skip] {source.source_id}: no collector registered")
            continue
        try:
            raw_items = collector.collect(source)
            normalized = normalize_many(raw_items)
            deduped = dedup_by_title(normalized)
            total_collected += len(deduped)
            inserted = 0
            if not args.dry_run:
                for item in deduped:
                    ok, _ = db.insert_raw_item(item)
                    if ok:
                        inserted += 1
                total_inserted += inserted
            print(f"[ok]   {source.source_id:<11} "
                  f"collected={len(deduped):<4} inserted={inserted}")
        except Exception as e:
            failures.append((source.source_id, str(e)))
            print(f"[fail] {source.source_id}: {e}")
            if args.verbose:
                traceback.print_exc()

    run.source_count = len(sources) - len(failures)
    run.raw_item_count = total_inserted
    if failures:
        run.finish(status="partial", error=f"{len(failures)} source(s) failed: {failures}")
    else:
        run.finish(status="ok")
    if not args.dry_run:
        db.finish_run(run_id, run.source_count, run.raw_item_count, run.status, run.error)

    print(f"\n--- summary ---")
    print(f"sources run:    {run.source_count}")
    print(f"items collected: {total_collected}")
    print(f"items inserted:  {total_inserted}")
    print(f"failures:        {len(failures)}")
    if failures:
        for sid, err in failures:
            print(f"  - {sid}: {err}")
    return 0 if not failures else 1


def cmd_filter_prompt(args, registry, db) -> int:
    from .analyze.filter import FilterPipeline
    pipe = FilterPipeline(db, llm=None)  # llm only needed for run(), not prompt dump
    items = pipe.fetch_batch(limit=args.limit, source_id=args.source,
                             only_unprocessed=not args.include_processed)
    if not items:
        print("no items to judge (limit={}, source={}, include_processed={})".format(
            args.limit, args.source, args.include_processed))
        return 0
    from .analyze.filter import build_judgment_prompt, items_for_prompt
    prompt = build_judgment_prompt(items)
    payload = {
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "item_count": len(items),
        "items_compact": items_for_prompt(items),
        "items": items,
        "prompt": prompt,
    }
    out = args.out
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote prompt payload ({len(items)} items) to {out}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_signals(args, registry, db) -> int:
    from .analyze.schema import CATEGORIES, IMPORTANCE_LEVELS, Signal
    path = Path(args.file)
    if not path.exists():
        print(f"file not found: {path}", file=sys.stderr)
        return 2
    data = json.loads(path.read_text(encoding="utf-8"))
    # accept either {"judgments":[...]} or [...] directly
    judgments = data["judgments"] if isinstance(data, dict) and "judgments" in data else data

    # Look up source URLs for each raw_id so signals carry the link.
    needed_ids = sorted({j["raw_id"] for j in judgments if j.get("keep", False) and "raw_id" in j})
    url_by_raw: dict[int, str] = {}
    published_by_raw: dict[int, str | None] = {}
    if needed_ids:
        placeholders = ",".join("?" for _ in needed_ids)
        with db.connect() as conn:
            rows = conn.execute(
                f"SELECT id, url, published_at FROM raw_items WHERE id IN ({placeholders})",
                needed_ids,
            ).fetchall()
            for r in rows:
                url_by_raw[r["id"]] = r["url"]
                published_by_raw[r["id"]] = r["published_at"]

    written = 0
    skipped = 0
    invalid = 0
    for j in judgments:
        if not j.get("keep", False):
            skipped += 1
            continue
        rid = j.get("raw_id")
        if rid not in url_by_raw:
            invalid += 1
            continue
        sig = Signal(
            raw_item_ids=[rid],
            title=(j.get("summary") or "")[:200],
            summary=j.get("summary", ""),
            why_it_matters=j.get("why_it_matters", ""),
            business_angle=j.get("business_angle", ""),
            category=j.get("category", "其他") if j.get("category") in CATEGORIES else "其他",
            importance=j.get("importance", "MEDIUM") if j.get("importance") in IMPORTANCE_LEVELS else "MEDIUM",
            source_urls=[url_by_raw[rid]],
            published_at=published_by_raw.get(rid),
            confidence=max(0.0, min(1.0, float(j.get("confidence", 0.5)))),
            metadata={"judged_via": args.file},
        )
        if not sig.title or not sig.summary:
            invalid += 1
            continue
        db.insert_signal(sig)
        written += 1
    print(f"signals written: {written}, skipped (keep=false): {skipped}, invalid: {invalid}")
    return 0


def cmd_run_cycle(args, registry, db) -> int:
    """End-to-end cycle: ingest all enabled sources; if new items arrived,
    drop a pending prompt JSON for the assistant to pick up next turn.

    --staged runs fast tier first (writing fast-PENDING.json), then slow
    tier (writing slow-PENDING.json), so each phase has its own trigger.
    """
    if getattr(args, "staged", False):
        return _cmd_run_cycle_staged(args, registry, db)

    from .collectors import all_collectors
    from .normalize import normalize_many
    from .dedup import dedup_by_title
    from .analyze.filter import FilterPipeline, build_judgment_prompt, items_for_prompt
    import datetime as _dt

    collectors = {c.source_id: c for c in all_collectors()}
    enabled = registry.enabled()
    sources_run = 0
    items_inserted = 0
    failures = []
    for source in enabled:
        if args.tier != "all" and source.tier != args.tier:
            continue
        collector = collectors.get(source.source_id)
        if not collector:
            print(f"[skip] {source.source_id}: no collector registered")
            continue
        try:
            raw_items = collector.collect(source)
            items = dedup_by_title(normalize_many(raw_items))
            inserted = 0
            for item in items:
                ok, _ = db.insert_raw_item(item)
                if ok:
                    inserted += 1
            items_inserted += inserted
            sources_run += 1
            db.record_source_success(source.source_id)
        except Exception as e:
            failures.append((source.source_id, str(e)))
            # Track failure and auto-disable if threshold reached
            try:
                count, disabled = db.record_source_failure(source.source_id, str(e))
                if disabled:
                    failures.append((source.source_id,
                        f"auto-disabled after {count} consecutive failures"))
            except Exception:
                pass

    # Generate pending prompt if new items arrived
    pending_path = Path(args.pending_file)
    pending_path.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "started_at": _dt.datetime.utcnow().isoformat() + "Z",
        "sources_run": sources_run,
        "items_inserted": items_inserted,
        "failures": failures,
        "pending_prompt": None,
    }

    if items_inserted > 0 or args.force_prompt:
        pipe = FilterPipeline(db, llm=None)
        items_to_judge = pipe.fetch_batch(limit=args.prompt_limit, only_unprocessed=True)
        if items_to_judge:
            payload = {
                "generated_at": _dt.datetime.utcnow().isoformat() + "Z",
                "phase": getattr(args, "phase", "auto"),
                "item_count": len(items_to_judge),
                "items": items_to_judge,
                "items_compact": items_for_prompt(items_to_judge),
                "prompt": build_judgment_prompt(items_to_judge),
            }
            pending_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            summary["pending_prompt"] = str(pending_path)
            summary["pending_count"] = len(items_to_judge)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    db.finish_run(
        db.start_run(),
        source_count=sources_run,
        raw_item_count=items_inserted,
        status="ok" if not failures else "partial",
        error=f"{len(failures)} source(s) failed" if failures else None,
    )
    return 0


def _cmd_run_cycle_staged(args, registry, db) -> int:
    """Run fast tier first, then slow tier, each writing its own pending file.

    Output: two JSON blocks prefixed with [phase:fast] and [phase:slow].
    """
    import datetime as _dt
    import copy as _copy

    base_pending = Path(args.pending_file)
    fast_path = base_pending.with_name(f"{base_pending.stem}-fast.json")
    slow_path = base_pending.with_name(f"{base_pending.stem}-slow.json")
    base_args = _copy.copy(args)

    # ── phase 1: fast ──────────────────────────────────────────────
    print(f"=== [phase:fast] starting at {_dt.datetime.utcnow().isoformat()}Z ===", flush=True)
    base_args.tier = "fast"
    base_args.pending_file = str(fast_path)
    base_args.phase = "fast"
    base_args.force_prompt = False
    base_args.staged = False  # ← critical: clear staged flag so recursive call doesn't re-enter staged mode
    cmd_run_cycle(base_args, registry, db)
    print(f"=== [phase:fast] done — pending={fast_path} ===\n", flush=True)

    # ── phase 2: slow ──────────────────────────────────────────────
    print(f"=== [phase:slow] starting at {_dt.datetime.utcnow().isoformat()}Z ===", flush=True)
    base_args.tier = "slow"
    base_args.pending_file = str(slow_path)
    base_args.phase = "slow"
    base_args.force_prompt = False
    base_args.staged = False  # ← same here
    cmd_run_cycle(base_args, registry, db)
    print(f"=== [phase:slow] done — pending={slow_path} ===", flush=True)
    return 0


def cmd_filter(args, registry, db) -> int:
    """End-to-end filter: fetch raw_items -> prompt the assistant -> write signals."""
    from .analyze.filter import FilterPipeline
    from .analyze.llm import make_llm
    try:
        llm = make_llm(name=args.llm, write_to_file=args.write_prompt)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    pipe = FilterPipeline(db, llm)
    result = pipe.run(limit=args.limit, source_id=args.source)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_report(args, registry, db) -> int:
    """Generate a structured daily report from signals table (JSON)."""
    import datetime as _dt
    since = (_dt.datetime.utcnow() - _dt.timedelta(days=args.days)).isoformat() + "Z"
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, title, summary, why_it_matters, business_angle, "
            "category, importance, confidence, source_urls, published_at, created_at "
            "FROM signals WHERE created_at >= ? "
            "ORDER BY (CASE importance WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END), "
            "confidence DESC",
            (since,),
        ).fetchall()
    all_rows = [dict(r) for r in rows]
    high = all_rows[: args.top]
    med = [r for r in all_rows if r["importance"] == "MEDIUM"][:6]
    from collections import Counter
    cats = Counter(r["category"] for r in all_rows)
    out = {
        "since": since,
        "totals": {
            "signals": len(all_rows),
            "high": sum(1 for r in all_rows if r["importance"] == "HIGH"),
            "medium": sum(1 for r in all_rows if r["importance"] == "MEDIUM"),
            "low": sum(1 for r in all_rows if r["importance"] == "LOW"),
            "raw_items": db.count_raw_items(),
        },
        "categories": dict(cats),
        "top_high": high,
        "top_medium": med,
    }
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote report ({len(all_rows)} signals) to {args.out}")
    else:
        print(text)
    return 0


def cmd_signals(args, registry, db) -> int:
    rows = db.list_signals(limit=args.limit, importance=args.importance)
    if not rows:
        print("no signals yet — run `radar filter-prompt` then `radar ingest-signals`")
        return 0
    for s in rows:
        urls = json.loads(s.get("source_urls") or "[]")
        print(f"\n[{s['importance']:<6}] {s['category']:<6} conf={s['confidence']:.2f}  {s['title']}")
        if s.get('why_it_matters'):
            print(f"  why:    {s['why_it_matters']}")
        if s.get('business_angle'):
            print(f"  angle:  {s['business_angle']}")
        for u in urls[:1]:
            print(f"  src:    {u}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="radar", description="AI Opportunity Radar CLI")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="path to sources.yaml")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="path to SQLite db")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sources", help="list registered sources")
    sub.add_parser("status", help="show DB stats + recent runs")

    p_recent = sub.add_parser("recent", help="show recently collected raw items")
    p_recent.add_argument("--limit", type=int, default=20)

    p_ingest = sub.add_parser("ingest", help="run collectors and write to DB")
    p_ingest.add_argument("--source", help="comma-separated list of source_ids (default: all enabled)")
    p_ingest.add_argument("--dry-run", action="store_true", help="collect but don't write to DB")
    p_ingest.add_argument("--verbose", "-v", action="store_true")

    p_filter = sub.add_parser("filter-prompt", help="dump a JSON payload of items + prompt for the LLM judge")
    p_filter.add_argument("--limit", type=int, default=15)
    p_filter.add_argument("--source", help="only items from this source_id")
    p_filter.add_argument("--include-processed", action="store_true",
                          help="include raw_items already used in a signal")
    p_filter.add_argument("--out", help="write payload to file instead of stdout")

    p_ingest_s = sub.add_parser("ingest-signals", help="ingest a judgments JSON file into signals table")
    p_ingest_s.add_argument("file", help="path to JSON file with shape {judgments:[...]} or [...]")

    p_run_cycle = sub.add_parser("run-cycle", help="ingest all enabled + drop pending prompt if new items (for automation)")
    p_run_cycle.add_argument("--prompt-limit", type=int, default=25)
    p_run_cycle.add_argument("--pending-file", default="/tmp/radar_pending.json",
                             help="path to write the pending prompt JSON")
    p_run_cycle.add_argument("--force-prompt", action="store_true",
                             help="always drop a prompt even if nothing new arrived")
    p_run_cycle.add_argument("--tier", choices=["fast", "slow", "all"], default="all",
                             help="fast = quick RSS + small APIs (~30s); slow = Reddit fan-in + GitHub Releases + HN (~2min); all = both")
    p_run_cycle.add_argument("--staged", action="store_true",
                             help="run fast tier first, then slow tier, each writing its own pending file (fast-PENDING.json and slow-PENDING.json)")
    p_run_cycle.add_argument("--phase", choices=["auto", "fast", "slow"], default="auto",
                             help="phase tag written into pending JSON (default auto uses current tier)")

    p_ingest_fast = sub.add_parser("ingest-fast", help="alias for 'run-cycle --tier fast' (convenience for automation)")
    p_ingest_fast.add_argument("--pending-file", default="/tmp/radar_pending_fast.json")
    p_ingest_slow = sub.add_parser("ingest-slow", help="alias for 'run-cycle --tier slow' (convenience for automation)")
    p_ingest_slow.add_argument("--pending-file", default="/tmp/radar_pending_slow.json")

    p_report = sub.add_parser("report", help="generate a structured daily report (JSON) from signals table")
    p_report.add_argument("--days", type=int, default=2, help="look back N days")
    p_report.add_argument("--top", type=int, default=10, help="max HIGH signals to include")
    p_report.add_argument("--out", help="write JSON report to file instead of stdout")

    p_filter_run = sub.add_parser("filter", help="fetch raw_items, prompt the assistant, write signals")
    p_filter_run.add_argument("--llm", choices=["manual"], default="manual",
                              help="LLM provider. Only 'manual' is supported - the OpenClaw assistant IS the filter.")
    p_filter_run.add_argument("--limit", type=int, default=20)
    p_filter_run.add_argument("--source", help="only items from this source_id")
    p_filter_run.add_argument("--write-prompt", help="(manual) write prompt to file instead of stdin")

    p_signals = sub.add_parser("signals", help="list generated signals")
    p_signals.add_argument("--limit", type=int, default=20)
    p_signals.add_argument("--importance", choices=["HIGH", "MEDIUM", "LOW"])

    args = parser.parse_args(argv)

    registry = load_registry(args.config)
    db = Database(args.db)

    # sync source registry into DB so dashboards show everything
    for s in registry.all():
        db.upsert_source({
            "source_id": s.source_id,
            "name": s.name,
            "country": s.country,
            "category": s.category,
            "type": s.type,
            "url": s.url,
            "api_endpoint": s.api_endpoint,
            "rss_url": s.rss_url,
            "legal_level": s.legal_level,
            "update_frequency": s.update_frequency,
            "enabled": 1 if s.enabled else 0,
            "priority": s.priority,
            "notes": s.notes,
            "metadata_json": json.dumps(s.extra, ensure_ascii=False) if s.extra else None,
        })

    if args.cmd == "sources":
        return cmd_sources(args, registry, db)
    if args.cmd == "status":
        return cmd_status(args, registry, db)
    if args.cmd == "recent":
        return cmd_recent(args, registry, db)
    if args.cmd == "ingest":
        return cmd_ingest(args, registry, db)
    if args.cmd == "run-cycle":
        return cmd_run_cycle(args, registry, db)
    if args.cmd == "ingest-fast":
        args.tier = "fast"
        return cmd_run_cycle(args, registry, db)
    if args.cmd == "ingest-slow":
        args.tier = "slow"
        return cmd_run_cycle(args, registry, db)
    if args.cmd == "report":
        return cmd_report(args, registry, db)
    if args.cmd == "filter-prompt":
        return cmd_filter_prompt(args, registry, db)
    if args.cmd == "filter":
        return cmd_filter(args, registry, db)
    if args.cmd == "ingest-signals":
        return cmd_ingest_signals(args, registry, db)
    if args.cmd == "signals":
        return cmd_signals(args, registry, db)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())