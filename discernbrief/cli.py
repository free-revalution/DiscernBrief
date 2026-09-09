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
    total_signals = db.count_signals()
    unsynced = db.count_unsynced_signals()
    enabled = len(registry.enabled())
    disabled = len([s for s in registry.all() if not s.enabled])
    print(f"DB:           {db.path}")
    print(f"raw_items:    {total_items}")
    print(f"signals:      {total_signals}  (unsynced: {unsynced})")
    print(f"enabled:      {enabled} / {len(registry)} sources  (auto-disabled: {disabled})")
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
        # raw_id lookup may miss for HN/V2EX/GoogleNews items that were
        # sourced from a stale slow-tier fallback (raw_items table has no
        # row for them). In that case still write the signal, but without
        # source_urls (we don't have the URL from this ingestion path).
        missing_url = rid not in url_by_raw
        if missing_url:
            url = None
        else:
            url = url_by_raw[rid]
        sig = Signal(
            raw_item_ids=[rid] if not missing_url else [],
            title=(j.get("summary") or "")[:200],
            summary=j.get("summary", ""),
            why_it_matters=j.get("why_it_matters", ""),
            business_angle=j.get("business_angle", ""),
            category=j.get("category", "其他") if j.get("category") in CATEGORIES else "其他",
            importance=j.get("importance", "MEDIUM") if j.get("importance") in IMPORTANCE_LEVELS else "MEDIUM",
            source_urls=[url] if url else [],
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
            import signal as _sig
            def _timeout_handler(signum, frame):
                raise TimeoutError(f"collector for {source.source_id} exceeded 90s")
            _sig.signal(_sig.SIGALRM, _timeout_handler)
            _sig.alarm(90)
            try:
                raw_items = collector.collect(source)
                items = dedup_by_title(normalize_many(raw_items))
            finally:
                _sig.alarm(0)
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


def cmd_backup(args, registry, db) -> int:
    """Backup SQLite DB. Writes .sql (full dump) + per-table .csv. Optionally git push.

    Use this for long-term archival + as the data source for OpenClaw quantitative
    analysis (cycles, category trends, source diversity, etc.). The CSV files are
    easy to load into pandas/DuckDB/Excel for ad-hoc analysis.
    """
    import csv as _csv
    import datetime as _dt
    import subprocess as _sp
    from pathlib import Path as _P

    out_dir = _P(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    # staleness-safe: if a backup for the current minute already exists, bump
    suffix = ""
    i = 0
    while (out_dir / f"{stamp}{suffix}").exists():
        i += 1; suffix = f"-{i}"
    target = out_dir / f"{stamp}{suffix}"
    target.mkdir(exist_ok=True)

    fmt = args.format
    written = []
    with db.connect() as conn:
        if fmt in ("sql", "all"):
            sql_file = target / "discernbrief.sql"
            with open(sql_file, "w", encoding="utf-8") as f:
                for line in conn.iterdump():
                    f.write(f"{line}\n")
            written.append(str(sql_file))
        if fmt in ("csv", "all"):
            for table in ["sources", "raw_items", "signals", "signal_raw_items", "runs"]:
                try:
                    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                except Exception as e:
                    print(f"  skip {table}: {e}")
                    continue
                if not rows:
                    continue
                csv_file = target / f"{table}.csv"
                with open(csv_file, "w", newline="", encoding="utf-8") as f:
                    w = _csv.writer(f)
                    w.writerow(rows[0].keys())
                    for r in rows:
                        w.writerow([_to_csv_cell(v) for v in r])
                written.append(str(csv_file))

    print(f"=== backup {stamp} ===")
    for p in written:
        print(f"  {p}")
    if not written:
        print("  (nothing written)")
        return 1

    if args.push:
        # Resolve to absolute paths first — Path.is_relative_to() needs both sides
        # absolute to compare correctly. Without resolve(), relative paths like
        # "backups/..." silently fail is_relative_to() checks against an absolute cwd.
        try:
            cwd_abs = _P.cwd().resolve()
            rel = [str(_P(p).resolve().relative_to(cwd_abs)) for p in written]
        except Exception as e:
            print(f"  resolve failed ({e}), falling back to whole-dir add")
            rel = ["./backups/"]
        if not rel:
            rel = ["./backups/"]
        msg = args.commit_msg or f"backup: {stamp} ({len(rel)} files)"
        for cmd in [["git", "add", "--"] + rel, ["git", "commit", "-m", msg], ["git", "push"]]:
            r = _sp.run(cmd, capture_output=True, text=True)
            tag = " ".join(cmd[:2])
            if r.returncode != 0 and "nothing to commit" not in r.stdout:
                print(f"  git {tag}: rc={r.returncode} stderr={r.stderr.strip()[:200]}")
            else:
                print(f"  git {tag}: ok")
    return 0


def _to_csv_cell(v):
    if v is None: return ""
    if isinstance(v, (dict, list)):
        import json as _json
        return _json.dumps(v, ensure_ascii=False)
    s = str(v)
    if any(c in s for c in (",", "\"", "\n", "\r")):
        return '"' + s.replace('"', '""') + '"'
    return s


_QUERY_PRESETS = {
    "summary": """
        SELECT
          (SELECT COUNT(*) FROM signals)                          AS total_signals,
          (SELECT COUNT(*) FROM signals WHERE importance='HIGH')   AS high_signals,
          (SELECT COUNT(*) FROM signals WHERE importance='MEDIUM') AS medium_signals,
          (SELECT COUNT(*) FROM raw_items)                         AS total_raw_items,
          (SELECT COUNT(*) FROM sources WHERE enabled=1)            AS enabled_sources,
          (SELECT MIN(created_at) FROM signals)                     AS earliest_signal,
          (SELECT MAX(created_at) FROM signals)                     AS latest_signal
    """,
    "daily": """
        SELECT DATE(created_at) AS day,
               SUM(CASE WHEN importance='HIGH'   THEN 1 ELSE 0 END) AS high,
               SUM(CASE WHEN importance='MEDIUM' THEN 1 ELSE 0 END) AS medium,
               SUM(CASE WHEN importance='LOW'    THEN 1 ELSE 0 END) AS low,
               COUNT(*) AS total
        FROM signals
        WHERE created_at >= datetime('now', '-' || :days || ' days')
        GROUP BY day
        ORDER BY day DESC
    """,
    "weekly": """
        SELECT strftime('%Y-W%W', created_at) AS week,
               SUM(CASE WHEN importance='HIGH'   THEN 1 ELSE 0 END) AS high,
               SUM(CASE WHEN importance='MEDIUM' THEN 1 ELSE 0 END) AS medium,
               COUNT(*) AS total
        FROM signals
        WHERE created_at >= datetime('now', '-' || :days || ' days')
        GROUP BY week
        ORDER BY week DESC
    """,
    "monthly": """
        SELECT strftime('%Y-%m', created_at) AS month,
               COUNT(*) AS total,
               SUM(CASE WHEN importance='HIGH' THEN 1 ELSE 0 END) AS high
        FROM signals
        WHERE created_at >= datetime('now', '-' || :days || ' days')
        GROUP BY month
        ORDER BY month DESC
    """,
    "categories": """
        SELECT category,
               COUNT(*) AS total,
               SUM(CASE WHEN importance='HIGH' THEN 1 ELSE 0 END) AS high,
               ROUND(100.0 * SUM(CASE WHEN importance='HIGH' THEN 1 ELSE 0 END) / COUNT(*), 1) AS high_pct
        FROM signals
        WHERE created_at >= datetime('now', '-' || :days || ' days')
        GROUP BY category
        ORDER BY total DESC
    """,
    "sources": """
        SELECT s.source_id, s.name, s.category,
               COUNT(DISTINCT ri.id) AS raw_items,
               COUNT(DISTINCT sig.id) AS signals
        FROM sources s
        LEFT JOIN raw_items ri ON ri.source_id = s.source_id
        LEFT JOIN signal_raw_items sri ON sri.raw_id = ri.id
        LEFT JOIN signals sig ON sig.id = sri.signal_id
        WHERE s.enabled = 1
        GROUP BY s.source_id
        ORDER BY signals DESC, raw_items DESC
    """,
    "importance": """
        SELECT importance, COUNT(*) AS n
        FROM signals
        WHERE created_at >= datetime('now', '-' || :days || ' days')
        GROUP BY importance
        ORDER BY n DESC
    """,
    "cycles": """
        SELECT CASE strftime('%w', created_at)
                 WHEN '0' THEN 'Sun' WHEN '1' THEN 'Mon' WHEN '2' THEN 'Tue'
                 WHEN '3' THEN 'Wed' WHEN '4' THEN 'Thu' WHEN '5' THEN 'Fri'
                 WHEN '6' THEN 'Sat' END AS weekday,
               COUNT(*) AS n
        FROM signals
        WHERE created_at >= datetime('now', '-' || :days || ' days')
        GROUP BY weekday
        ORDER BY n DESC
    """,
    "trends": """
        SELECT category, strftime('%Y-W%W', created_at) AS week, COUNT(*) AS n
        FROM signals
        WHERE created_at >= datetime('now', '-' || :days || ' days')
        GROUP BY category, week
        ORDER BY week DESC, n DESC
    """,
    "recent": """
        SELECT id, created_at, category, importance, confidence, title
        FROM signals
        ORDER BY id DESC
        LIMIT :limit
    """,
    "topurls": """
        SELECT
          substr(url, instr(url, '//') + 2,
                 CASE WHEN instr(substr(url, instr(url, '//') + 3), '/') > 0
                      THEN instr(substr(url, instr(url, '//') + 3), '/') - 1
                      ELSE length(url) END) AS domain,
          COUNT(*) AS n
        FROM raw_items
        WHERE url IS NOT NULL AND url != ''
        GROUP BY domain
        ORDER BY n DESC
        LIMIT :limit
    """,
}


def cmd_query(args, registry, db) -> int:
    """Run analysis queries against the signals DB. OpenClaw can call --sql
    directly or use --preset for common quantitative-analysis patterns."""
    import csv as _csv
    import io as _io

    if not args.sql and not args.preset:
        print("specify --preset <name> or --sql '...'", file=sys.stderr)
        print(f"presets: {', '.join(_QUERY_PRESETS.keys())}", file=sys.stderr)
        return 2

    if args.sql:
        sql = args.sql.strip().rstrip(";")
        params = {}
        title = "custom SQL"
    else:
        sql = _QUERY_PRESETS[args.preset].strip()
        params = {"days": args.days, "limit": args.limit}
        title = f"preset={args.preset} (days={args.days})"

    with db.connect() as conn:
        try:
            cur = conn.execute(sql, params)
        except Exception as e:
            print(f"SQL error: {e}", file=sys.stderr)
            print(f"--- SQL ---\n{sql}\n---", file=sys.stderr)
            return 1
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    print(f"=== {title} ===  rows={len(rows)}")
    if not rows:
        return 0

    if args.format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.format == "csv":
        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow(cols)
        for r in rows:
            w.writerow([_to_csv_cell(r.get(c)) for c in cols])
        print(buf.getvalue())
        return 0

    widths = {c: max(len(c), max((len(_to_csv_cell(r.get(c) or "")) for r in rows), default=0)) for c in cols}
    sep = "  "
    print(sep.join(c.ljust(widths[c]) for c in cols))
    print(sep.join("-" * widths[c] for c in cols))
    for r in rows:
        print(sep.join((_to_csv_cell(r.get(c)) or "").ljust(widths[c]) for c in cols))
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


def cmd_sync_bitable(args, registry, db) -> int:
    """Sync local signals to two Feishu Bitable tables (Data + Opportunities)."""
    import urllib.request, urllib.error, json as _json
    import subprocess as _sp
    from datetime import datetime, timezone
    from pathlib import Path

    DATA = ("KJynbSctXazjQns64Itc1P7ynAf", "tblE3VweAw4QPWCg", "Data")
    OPPS = ("Wfn6bhMwtaixeFsUsfscV1v2nZW", "tblDuiodjLiM6OZw", "Opportunities")
    CREDS_PATH = Path.home() / ".openclaw" / "feishu_creds.json"

    def http(url, payload, token, method="POST", max_retries=4):
        """curl subprocess + retry. Python urllib kept hitting SSL EOF on Feishu."""
        import subprocess, time as _time
        args = ["curl", "-sS", "-L", "--max-time", "30",
                "-H", "Content-Type: application/json; charset=utf-8",
                "-H", f"Authorization: Bearer {token}",
                "-X", method]
        if payload is not None:
            args += ["-d", _json.dumps(payload)]
        args.append(url)
        for attempt in range(max_retries + 1):
            try:
                r = subprocess.run(args, capture_output=True, text=True, timeout=40)
            except subprocess.TimeoutExpired:
                if attempt < max_retries:
                    _time.sleep(1.5 * (attempt + 1)); continue
                return None, {"curl_timeout": True}
            if r.returncode != 0:
                if attempt < max_retries:
                    _time.sleep(1.5 * (attempt + 1)); continue
                return None, {"curl_rc": r.returncode, "stderr": (r.stderr or "")[:200]}
            try:
                return 200, _json.loads(r.stdout)
            except _json.JSONDecodeError:
                return r.returncode, {"raw": (r.stdout or "")[:500]}
        return None, {"retries_exhausted": True}

    def iso_to_ms(s):
        if not s: return None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1000)
        except Exception:
            return None

    def to_url(signal):
        try:
            urls = _json.loads(signal.get("source_urls") or "[]")
            return urls[0] if urls else ""
        except Exception:
            return ""

    def to_raw_ids(signal):
        try: return _json.loads(signal.get("raw_item_ids") or "[]")
        except Exception: return []

    def fetch_source_id(db, raw_ids):
        if not raw_ids: return ""
        try:
            with db.connect() as conn:
                placeholders = ",".join("?" for _ in raw_ids)
                row = conn.execute(
                    f"SELECT source_id FROM raw_items WHERE id IN ({placeholders}) LIMIT 1",
                    list(raw_ids),
                ).fetchone()
                return row["source_id"] if row else ""
        except Exception:
            return ""

    def fetch_source_name(registry, source_id):
        if not source_id: return ""
        try:
            s = registry.get(source_id)
            return s.name
        except Exception:
            return source_id

    # Load creds + get fresh token
    if not CREDS_PATH.exists():
        print(f"ERROR: {CREDS_PATH} not found. Store App ID + App Secret there first.", file=sys.stderr)
        return 1
    creds = _json.loads(CREDS_PATH.read_text())
    app_id = creds["app_id"]; app_secret = creds["app_secret"]; del creds
    c, d = http("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                {"app_id": app_id, "app_secret": app_secret}, "x")
    if c != 200 or d.get("code") != 0:
        print(f"token failed: {c} {d}"); return 1
    token = d["tenant_access_token"]
    del app_id, app_secret
    print(f"=== token OK (expire={d.get('expire')}s) ===\n", flush=True)

    def upsert(app_token, tid, fields, record_id=None):
        """Create or update a Bitable record. fields dict is the body."""
        if record_id:
            c, d = http(f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{tid}/records/{record_id}",
                        {"fields": fields}, token, method="PUT")
        else:
            c, d = http(f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{tid}/records",
                        {"fields": fields}, token, method="POST")
        if c != 200 or d.get("code") != 0:
            return None, f"http={c} resp={d.get('msg', str(d)[:120])}"
        return d.get("data", {}).get("record", {}).get("record_id"), None

    def find_by_raw_id(app_token, tid, raw_id):
        c, d = http(
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{tid}/records/search",
            {"filter": {"conjunction": "and", "conditions": [{"field_name": "raw_id", "operator": "is", "value": [str(raw_id)]}]}}, token, method="POST")
        if c != 200 or d.get("code") != 0: return None
        items = d.get("data", {}).get("items", []) or []
        return items[0].get("record_id") if items else None

    # Fetch un-synced signals
    signals = db.unsynced_signals()
    only_high = bool(args.only_high)
    print(f"=== {len(signals)} un-synced signal(s) in local DB ===", flush=True)
    if args.dry_run:
        print("(DRY RUN — no writes)\n", flush=True)
    if not signals:
        print("(nothing to do)"); return 0

    written_data = 0; written_opps = 0
    errors = []
    for i, sig in enumerate(signals, 1):
        rid = sig["id"]
        title = (sig.get("title") or "")[:200]
        category = sig.get("category") or "其他"
        importance = sig.get("importance") or "MEDIUM"
        summary = sig.get("summary") or ""
        url = to_url(sig)
        raw_ids = to_raw_ids(sig)
        source_id = fetch_source_id(db, raw_ids)
        source_name = fetch_source_name(registry, source_id)
        why = sig.get("why_it_matters") or ""
        angle = sig.get("business_angle") or ""
        conf = float(sig.get("confidence") or 0.5)
        pub_ms = iso_to_ms(sig.get("published_at"))
        crt_ms = iso_to_ms(sig.get("created_at"))

        # Data table fields
        data_fields = {
            "title":        title,
            "url":          {"link": url or "https://example.com/no-url", "text": (title[:60] or "(no title)")},
            "source_id":    source_id,
            "source_name":  source_name,
            "category":     category,
            "importance":   importance,
            "summary":      summary,
            "raw_id":       rid,
        }
        if pub_ms:  data_fields["published_at"] = pub_ms
        if crt_ms:  data_fields["collected_at"] = crt_ms

        # Opportunities table fields (only for HIGH by default, or MEDIUM if --include-medium)
        opps_fields = None
        if importance == "HIGH" or (not only_high and importance == "MEDIUM" and angle):
            opps_fields = {
                "title":        title,
                "url":          {"link": url or "https://example.com/no-url", "text": (title[:60] or "(no title)")},
                "category":     category,
                "importance":   importance,
                "summary":      summary,
                "why_it_matters": why,
                "business_angle": angle,
                "confidence":   conf,
                "source_id":    source_id,
                "source_data_raw_id": rid,
            }
            if pub_ms:  opps_fields["published_at"]   = pub_ms
            if crt_ms:  opps_fields["judged_at"]       = crt_ms

        if args.dry_run:
            tag = " (would sync to Opps)" if opps_fields else ""
            print(f"  [{i:>3}/{len(signals)}] raw_id={rid} {importance:<6} {category:<6} {title[:60]}{tag}")
            continue

        # Upsert Data
        data_rid = find_by_raw_id(DATA[0], DATA[1], rid)
        if data_rid:
            new_rid, err = upsert(DATA[0], DATA[1], data_fields, data_rid)
        else:
            new_rid, err = upsert(DATA[0], DATA[1], data_fields, None)
        if err:
            errors.append((rid, "data", err))
            print(f"  [{i:>3}] raw_id={rid} Data FAIL: {err}")
            continue
        written_data += 1

        # Upsert Opportunities (if applicable)
        opps_rid = None
        if opps_fields:
            opps_rid_existing = find_by_raw_id(OPPS[0], OPPS[1], rid)
            if opps_rid_existing:
                opps_rid, err = upsert(OPPS[0], OPPS[1], opps_fields, opps_rid_existing)
            else:
                opps_rid, err = upsert(OPPS[0], OPPS[1], opps_fields, None)
            if err:
                errors.append((rid, "opps", err))
                print(f"  [{i:>3}] raw_id={rid} Opps FAIL: {err}")
                # still mark data as synced
            else:
                written_opps += 1

        # Mark synced
        db.mark_signal_synced(rid, new_rid, opps_rid)
        print(f"  [{i:>3}/{len(signals)}] raw_id={rid} {importance:<6} {category:<6} → Data {'UPD' if data_rid else 'NEW'}{' +Opps' if opps_rid else ''}")

    print()
    if args.dry_run:
        print("(dry run) — run without --dry-run to actually write")
    else:
        print(f"=== sync done: Data {written_data} written, Opps {written_opps} written, errors {len(errors)} ===")
    if errors:
        print("errors:")
        for rid, where, err in errors[:5]:
            print(f"  raw_id={rid} {where}: {err}")
    return 0 if not errors else 1


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

    p_export = sub.add_parser("export-xlsx", help="export signals+raw_items to .xlsx (for daily morning briefing)")
    p_export.add_argument("--days", type=int, default=1)
    p_export.add_argument("--out", required=True, help="output .xlsx path")

    p_signals = sub.add_parser("signals", help="list generated signals")
def cmd_export_xlsx(args, registry, db) -> int:
    """Export signals/raw_items to Excel (for daily morning briefing)."""
    import xlsxwriter
    from datetime import datetime, timezone, timedelta
    days = int(args.days)
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with db.connect() as conn:
        sigs = conn.execute("""
            SELECT id,title,summary,why_it_matters,business_angle,
                   category,importance,confidence,source_urls,published_at,created_at
            FROM signals WHERE created_at >= ?
            ORDER BY (CASE importance WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END),
                     confidence DESC, id DESC
        """, (since,)).fetchall()
        raws = conn.execute("""
            SELECT id,source_id,title,url,published_at,collected_at
            FROM raw_items WHERE collected_at >= ?
            ORDER BY collected_at DESC
        """, (since,)).fetchall()
    wb = xlsxwriter.Workbook(str(out))
    bold = wb.add_format({"bold": True, "bg_color": "#DDDDDD"})
    date_fmt = wb.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"})
    ws1 = wb.add_worksheet("signals")
    h1 = ["id","created_at","importance","category","title","summary",
          "why_it_matters","business_angle","confidence","url","published_at"]
    for c,h in enumerate(h1): ws1.write(0,c,h,bold)
    for ri,row in enumerate(sigs,1):
        for c,h in enumerate(h1):
            v = row[h] if h in row.keys() else ""
            if h == "created_at" and v:
                try: ws1.write_datetime(ri,c,datetime.fromisoformat(v),date_fmt); continue
                except: pass
            ws1.write(ri,c,str(v) if v is not None else "")
    ws1.set_column(0,len(h1)-1,24); ws1.freeze_panes(1,0)
    ws2 = wb.add_worksheet("raw_items")
    h2 = ["id","source_id","title","url","published_at","collected_at"]
    for c,h in enumerate(h2): ws2.write(0,c,h,bold)
    for ri,row in enumerate(raws,1):
        for c,h in enumerate(h2):
            v = row[h] if h in row.keys() else ""
            for dk in ("published_at","collected_at"):
                if h==dk and v:
                    try: ws2.write_datetime(ri,c,datetime.fromisoformat(v),date_fmt); break
                    except: pass
            else:
                ws2.write(ri,c,str(v) if v is not None else "")
    ws2.set_column(0,len(h2)-1,30); ws2.freeze_panes(1,0)
    wb.close()
    print(f"exported {len(sigs)} signals + {len(raws)} raw_items -> {out}")
    return 0



    p_signals.add_argument("--limit", type=int, default=20)
    p_signals.add_argument("--importance", choices=["HIGH", "MEDIUM", "LOW"])

    p_sync = sub.add_parser("sync-bitable", help="sync local signals to Feishu Bitable (Data + Opportunities tables)")
    p_sync.add_argument("--dry-run", action="store_true", help="preview only, no writes")
    p_sync.add_argument("--only-high", action="store_true",
                         help="Opportunities table only gets HIGH signals (default: HIGH + MEDIUM with business_angle)")

    p_backup = sub.add_parser("backup", help="backup SQLite DB to .sql + per-table .csv (for long-term archival + OpenClaw analysis)")
    p_backup.add_argument("--out", default="./backups", help="output directory (default ./backups)")
    p_backup.add_argument("--format", choices=["sql", "csv", "all"], default="all",
                          help="what to write: sql = .dump, csv = per-table, all = both (default)")
    p_backup.add_argument("--push", action="store_true",
                          help="also git add + commit + push (if in a git repo)")
    p_backup.add_argument("--commit-msg", default=None, help="custom git commit message (default: timestamped auto)")

    p_query = sub.add_parser("query", help="run analysis queries against the signals DB (for OpenClaw quantitative analysis)")
    p_query.add_argument("--sql", help="raw SQL to run (mutually exclusive with --preset)")
    p_query.add_argument("--preset", choices=[
                          "daily", "weekly", "monthly", "categories", "sources",
                          "importance", "cycles", "trends", "recent", "topurls", "summary",
                        ], help="pre-built analysis query")
    p_query.add_argument("--days", type=int, default=30, help="look back N days (default 30)")
    p_query.add_argument("--limit", type=int, default=20, help="row limit (for recent / topurls)")
    p_query.add_argument("--format", choices=["table", "json", "csv"], default="table", help="output format")

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
    if args.cmd == "sync-bitable":
        return cmd_sync_bitable(args, registry, db)
    if args.cmd == "export-xlsx":
        return cmd_export_xlsx(args, registry, db)
    if args.cmd == "backup":
        return cmd_backup(args, registry, db)
    if args.cmd == "query":
        return cmd_query(args, registry, db)
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