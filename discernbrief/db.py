"""SQLite layer. Single-file DB, schema-on-open."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    source_id        TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    country          TEXT,
    category         TEXT,
    type             TEXT,
    url              TEXT,
    api_endpoint     TEXT,
    rss_url          TEXT,
    legal_level      TEXT,
    update_frequency TEXT,
    enabled          INTEGER NOT NULL DEFAULT 0,
    priority         TEXT,
    notes            TEXT,
    metadata_json    TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL,
    external_id     TEXT,
    url             TEXT NOT NULL,
    title           TEXT,
    content         TEXT,
    published_at    TEXT,
    collected_at    TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    metadata_json   TEXT,
    UNIQUE (source_id, external_id),
    UNIQUE (content_hash),
    FOREIGN KEY (source_id) REFERENCES sources(source_id)
);
CREATE INDEX IF NOT EXISTS idx_raw_items_source ON raw_items(source_id);
CREATE INDEX IF NOT EXISTS idx_raw_items_published ON raw_items(published_at);

CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    summary         TEXT,
    why_it_matters  TEXT,
    business_angle  TEXT,
    category        TEXT,
    importance      TEXT,
    confidence      REAL DEFAULT 0.5,
    raw_item_ids    TEXT,
    source_urls     TEXT,
    published_at    TEXT,
    created_at      TEXT NOT NULL
);

-- many-to-many so we can ask "which raw_items already belong to a signal?"
CREATE TABLE IF NOT EXISTS signal_raw_items (
    signal_id   INTEGER NOT NULL,
    raw_id      INTEGER NOT NULL,
    PRIMARY KEY (signal_id, raw_id),
    FOREIGN KEY (signal_id) REFERENCES signals(id) ON DELETE CASCADE,
    FOREIGN KEY (raw_id) REFERENCES raw_items(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_signal_raw_items_raw ON signal_raw_items(raw_id);

CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    source_count    INTEGER DEFAULT 0,
    raw_item_count  INTEGER DEFAULT 0,
    signal_count    INTEGER DEFAULT 0,
    status          TEXT,
    error           TEXT
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._migrate()

    def _migrate(self) -> None:
        """Lightweight additive migrations. Each statement is idempotent."""
        migrations = [
            # v0.1.0: add signals.confidence if missing (added after initial schema)
            ("signals", "confidence", "REAL DEFAULT 0.5"),
            # v0.2.0: source health tracking for auto-disable
            ("sources", "consecutive_failures", "INTEGER DEFAULT 0"),
            ("sources", "disabled_reason", "TEXT"),
            ("sources", "disabled_at", "TEXT"),
            # v0.3.0: bitable sync state
            ("signals", "synced_to_bitable_at", "TEXT"),
            ("signals", "bitable_data_record_id", "TEXT"),
            ("signals", "bitable_opps_record_id", "TEXT"),
        ]
        with self.connect() as conn:
            for table, column, decl in migrations:
                cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
                if column not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
            conn.commit()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    # ── sources ────────────────────────────────────────────────────────
    def upsert_source(self, row: dict) -> None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sources (source_id, name, country, category, type, url,
                                     api_endpoint, rss_url, legal_level, update_frequency,
                                     enabled, priority, notes, metadata_json, created_at, updated_at)
                VALUES (:source_id, :name, :country, :category, :type, :url,
                        :api_endpoint, :rss_url, :legal_level, :update_frequency,
                        :enabled, :priority, :notes, :metadata_json, :created_at, :updated_at)
                ON CONFLICT(source_id) DO UPDATE SET
                    name=excluded.name,
                    category=excluded.category,
                    type=excluded.type,
                    url=excluded.url,
                    api_endpoint=excluded.api_endpoint,
                    rss_url=excluded.rss_url,
                    enabled=excluded.enabled,
                    priority=excluded.priority,
                    notes=excluded.notes,
                    updated_at=excluded.updated_at
                """,
                {**row, "created_at": now, "updated_at": now},
            )
            conn.commit()

    def all_sources(self) -> list[dict]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM sources ORDER BY source_id").fetchall()]

    def record_source_success(self, source_id: str) -> None:
        """Reset consecutive_failures counter on a successful fetch."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE sources SET consecutive_failures=0 WHERE source_id=?",
                (source_id,),
            )
            conn.commit()

    def record_source_failure(
        self,
        source_id: str,
        reason: str,
        *,
        auto_disable_threshold: int = 2,
    ) -> tuple[int, bool]:
        """Increment consecutive_failures; auto-disable when threshold hit.

        Default threshold is 2 (per user spec: 'if >2 consecutive failures, disable').
        Returns (new_failure_count, was_auto_disabled).
        """
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                "UPDATE sources SET consecutive_failures = consecutive_failures + 1 "
                "WHERE source_id=?",
                (source_id,),
            )
            row = conn.execute(
                "SELECT consecutive_failures FROM sources WHERE source_id=?",
                (source_id,),
            ).fetchone()
            count = row["consecutive_failures"] if row else 0
            disabled = False
            if count >= auto_disable_threshold:
                # only auto-disable sources that are currently enabled
                cur = conn.execute(
                    "UPDATE sources SET enabled=0, disabled_reason=?, disabled_at=? "
                    "WHERE source_id=? AND enabled=1",
                    (f"auto-disabled after {count} consecutive failures: {reason}",
                     now, source_id),
                )
                disabled = cur.rowcount > 0
            conn.commit()
            return count, disabled

    # ── raw_items ──────────────────────────────────────────────────────
    def insert_raw_item(self, item) -> tuple[bool, int | None]:
        """Returns (inserted, id). inserted=False means duplicate (url or hash)."""
        row = item.to_db_row()
        with self.connect() as conn:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO raw_items (source_id, external_id, url, title, content,
                                           published_at, collected_at, content_hash, metadata_json)
                    VALUES (:source_id, :external_id, :url, :title, :content,
                            :published_at, :collected_at, :content_hash, :metadata_json)
                    """,
                    row,
                )
                conn.commit()
                return True, cur.lastrowid
            except sqlite3.IntegrityError:
                return False, None

    def count_raw_items(self, source_id: str | None = None) -> int:
        with self.connect() as conn:
            if source_id:
                r = conn.execute("SELECT COUNT(*) AS n FROM raw_items WHERE source_id = ?", (source_id,)).fetchone()
            else:
                r = conn.execute("SELECT COUNT(*) AS n FROM raw_items").fetchone()
            return r["n"]

    def recent_raw_items(self, limit: int = 20) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, source_id, title, url, published_at, collected_at FROM raw_items "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ── runs ───────────────────────────────────────────────────────────
    def start_run(self) -> int:
        from datetime import datetime, timezone
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO runs (started_at, status) VALUES (?, 'running')",
                (datetime.now(timezone.utc).isoformat(),),
            )
            conn.commit()
            return cur.lastrowid

    def finish_run(self, run_id: int, source_count: int, raw_item_count: int,
                   status: str = "ok", error: str | None = None) -> None:
        from datetime import datetime, timezone
        with self.connect() as conn:
            conn.execute(
                "UPDATE runs SET finished_at=?, source_count=?, raw_item_count=?, status=?, error=? "
                "WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), source_count, raw_item_count, status, error, run_id),
            )
            conn.commit()

    # ── signals ─────────────────────────────────────────────────────────
    def insert_signal(self, signal) -> int:
        """Insert a Signal. Returns the new signal id."""
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO signals (title, summary, why_it_matters, business_angle,
                                     category, importance, confidence, raw_item_ids,
                                     source_urls, published_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.title,
                    signal.summary,
                    signal.why_it_matters,
                    signal.business_angle,
                    signal.category,
                    signal.importance,
                    signal.confidence,
                    json.dumps(signal.raw_item_ids),
                    json.dumps(signal.source_urls),
                    signal.published_at,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            for raw_id in signal.raw_item_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO signal_raw_items (signal_id, raw_id) VALUES (?, ?)",
                    (cur.lastrowid, raw_id),
                )
            conn.commit()
            return cur.lastrowid

    def count_signals(self) -> int:
        with self.connect() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM signals").fetchone()["n"]

    def count_unsynced_signals(self) -> int:
        """Signals that have not yet been pushed to Feishu Bitable."""
        with self.connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) AS n FROM signals WHERE synced_to_bitable_at IS NULL"
            ).fetchone()["n"]


    def list_signals(self, limit: int = 20, importance: str | None = None) -> list[dict]:
        with self.connect() as conn:
            sql = "SELECT * FROM signals"
            params: list = []
            if importance:
                sql += " WHERE importance = ?"
                params.append(importance)
            sql += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def unsynced_signals(self) -> list[dict]:
        """Signals not yet synced to Feishu Bitable (oldest first)."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM signals WHERE synced_to_bitable_at IS NULL "
                "ORDER BY id ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_signal_synced(self, signal_id: int, data_record_id: str | None,
                           opps_record_id: str | None) -> None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                "UPDATE signals SET synced_to_bitable_at=?, "
                "bitable_data_record_id=COALESCE(?, bitable_data_record_id), "
                "bitable_opps_record_id=COALESCE(?, bitable_opps_record_id) "
                "WHERE id=?",
                (now, data_record_id, opps_record_id, signal_id),
            )
            conn.commit()

    def list_runs(self, limit: int = 10) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]