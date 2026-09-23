"""
SQLite database layer. One local file, created automatically on first run
together with the bootstrap ADMIN account (since there is no self-registration).
"""
import sqlite3
import threading
from contextlib import contextmanager

from . import config
from . import security

# A single re-entrant lock guards audit_log insertion so that "seq" and
# "previous_hash" are always read-and-appended atomically, even under
# concurrent requests. Documented and used in audit.py.
AUDIT_LOCK = threading.Lock()


def _connect() -> sqlite3.Connection:
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    config.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# One shared connection is fine for a single-process prototype server;
# sqlite3 handles internal locking, and AUDIT_LOCK guards the hash-chain
# read-then-append sequence specifically.
_CONN = _connect()


@contextmanager
def get_conn():
    try:
        yield _CONN
    finally:
        pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('ADMIN', 'INVESTIGATOR')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'OPEN',
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_members (
    case_id INTEGER NOT NULL REFERENCES cases(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    added_at TEXT NOT NULL,
    PRIMARY KEY (case_id, user_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id),
    filename TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    content_type TEXT NOT NULL DEFAULT '',
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    uploaded_at TEXT NOT NULL,
    exif_status TEXT NOT NULL DEFAULT 'NOT_APPLICABLE',
    exif_json TEXT NOT NULL DEFAULT '{}',
    category TEXT NOT NULL DEFAULT 'OTHER'
);

-- Chain-of-custody log. NOTE: this table intentionally stores only an
-- action CODE + JSON params, never a pre-built sentence, so the same row
-- can be rendered in Arabic or English at read time (see i18n.py).
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    actor_id INTEGER,
    action TEXT NOT NULL,
    case_id INTEGER,
    evidence_id INTEGER,
    ts TEXT NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}'
);

-- Caches the last successful "Run AI analysis" result per evidence item,
-- so it survives a page reload instead of needing to be re-run every
-- time (re-running is still one click away; this only avoids the result
-- disappearing on its own).
CREATE TABLE IF NOT EXISTS evidence_analysis (
    evidence_id INTEGER PRIMARY KEY REFERENCES evidence(id),
    result_json TEXT NOT NULL,
    lang TEXT NOT NULL,
    analyzed_at TEXT NOT NULL
);

-- Caches the last generated formal case summary. Auto-generated once
-- when the Overview tab is first opened with no summary yet; every
-- later refresh is manual, so new evidence does NOT silently change an
-- already-generated summary until the investigator asks for one.
CREATE TABLE IF NOT EXISTS case_summary (
    case_id INTEGER PRIMARY KEY REFERENCES cases(id),
    summary_text TEXT NOT NULL,
    lang TEXT NOT NULL,
    generated_at TEXT NOT NULL
);

-- Caches the last authenticity check (deterministic EXIF indicators +
-- approximate AI visual triage) per evidence item, same caching pattern
-- as evidence_analysis: auto-generated once, refreshed only on request.
CREATE TABLE IF NOT EXISTS evidence_authenticity (
    evidence_id INTEGER PRIMARY KEY REFERENCES evidence(id),
    result_json TEXT NOT NULL,
    lang TEXT NOT NULL,
    checked_at TEXT NOT NULL
);
"""


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """
    Lightweight migration: adds `column` to `table` if it doesn't already
    exist, so an existing storage/athar.db with real data upgrades in
    place on the next server start instead of needing to be deleted.
    `ddl` is the column type/default clause, e.g. "TEXT NOT NULL DEFAULT 'OTHER'".
    """
    existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn.commit()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.commit()

        # Migrations for columns added after the initial release -- safe
        # to run on every startup; a no-op once the column already exists.
        _ensure_column(conn, "evidence", "category", "TEXT NOT NULL DEFAULT 'OTHER'")

        cur = conn.execute("SELECT COUNT(*) AS c FROM users")
        if cur.fetchone()["c"] == 0:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) "
                "VALUES (?, ?, 'ADMIN', ?)",
                (
                    config.DEFAULT_ADMIN_USERNAME,
                    security.hash_password(config.DEFAULT_ADMIN_PASSWORD),
                    now,
                ),
            )
            conn.commit()