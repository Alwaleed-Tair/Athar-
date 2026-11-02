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
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


# One connection PER THREAD. A single connection shared by concurrent request
# threads interleaves cursors and transactions, which produced random 500s and
# even wrong 401/403 answers under parallel requests. SQLite in WAL mode lets
# these connections read concurrently; writes wait up to busy_timeout.
_local = threading.local()
_connect()  # create the storage directories / database file on import


def _thread_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
    return conn


@contextmanager
def get_conn():
    conn = _thread_conn()
    try:
        yield conn
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    else:
        # Safety net: never leave a write transaction open on a pooled
        # thread connection (it would hold the write lock for other requests).
        if conn.in_transaction:
            conn.commit()


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

-- Cached AI relationships for the evidence map (regenerated only when the
-- evidence changes or the user asks), so the map does not change on every visit.
CREATE TABLE IF NOT EXISTS case_map_ai (
    case_id INTEGER PRIMARY KEY REFERENCES cases(id),
    lang TEXT NOT NULL,
    signature TEXT NOT NULL,
    edges_json TEXT NOT NULL,
    generated_at TEXT NOT NULL
);

-- Optional semantic-search vectors (only when an embeddings provider is configured).
CREATE TABLE IF NOT EXISTS evidence_embeddings (
    evidence_id INTEGER PRIMARY KEY REFERENCES evidence(id),
    model TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    vector_json TEXT NOT NULL
);

-- One-time e-mail tokens (verification, password reset). Only a SHA-256 of the token is
-- stored, so a database leak does not leak usable links.
CREATE TABLE IF NOT EXISTS email_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    token_hash TEXT NOT NULL UNIQUE,
    purpose TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT
);

-- Full extracted text of an evidence item (derived data, rebuilt from the
-- untouched original file; removed when the evidence is deleted). Used
-- for search and similarity -- never for anything that alters the file.
CREATE TABLE IF NOT EXISTS evidence_text (
    evidence_id INTEGER PRIMARY KEY REFERENCES evidence(id),
    text TEXT NOT NULL,
    extracted_at TEXT NOT NULL
);

-- Parsed conversation (chat export) metadata + messages. Derived from the
-- original file, which is never modified. source_ref says where in the
-- original each message came from (line number / page).
CREATE TABLE IF NOT EXISTS conversations (
    evidence_id INTEGER PRIMARY KEY REFERENCES evidence(id),
    format TEXT NOT NULL,
    participants_json TEXT NOT NULL DEFAULT '[]',
    message_count INTEGER NOT NULL DEFAULT 0,
    first_ts TEXT,
    last_ts TEXT,
    truncated INTEGER NOT NULL DEFAULT 0,
    parsed_at TEXT NOT NULL,
    summary_json TEXT
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id INTEGER NOT NULL REFERENCES evidence(id),
    idx INTEGER NOT NULL,
    sender TEXT,
    ts TEXT,
    ts_raw TEXT,
    body TEXT NOT NULL,
    source_ref TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_ev ON chat_messages(evidence_id, idx);

CREATE TABLE IF NOT EXISTS contact_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    category TEXT NOT NULL,
    subject TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    emailed INTEGER NOT NULL DEFAULT 0,
    handled INTEGER NOT NULL DEFAULT 0
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
        _ensure_column(conn, "cases", "case_identifier", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "cases", "priority", "TEXT NOT NULL DEFAULT 'MEDIUM'")
        _ensure_column(conn, "cases", "classification", "TEXT NOT NULL DEFAULT 'RESTRICTED'")
        _ensure_column(conn, "users", "full_name", "TEXT NOT NULL DEFAULT ''")
        # Accounts that existed before e-mail verification are treated as
        # verified (default 1); new self-registrations insert 0 explicitly.
        _ensure_column(conn, "users", "email", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "users", "email_verified", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(conn, "users", "token_version", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "users", "updated_at", "TEXT")
        _ensure_column(conn, "users", "handle", "TEXT")
        _ensure_column(conn, "users", "deleted_at", "TEXT")
        _ensure_column(conn, "evidence_text", "source", "TEXT NOT NULL DEFAULT 'FILE'")
        # editable public username: backfill from the e-mail local part / username, made unique
        for u in conn.execute("SELECT id, username, email FROM users WHERE handle IS NULL AND deleted_at IS NULL").fetchall():
            base = ((u["email"] or u["username"]).split("@")[0] or f"user{u['id']}")[:30]
            cand, n = base, 1
            while conn.execute("SELECT 1 FROM users WHERE handle = ? COLLATE NOCASE", (cand,)).fetchone():
                n += 1
                cand = f"{base[:26]}{n}"
            conn.execute("UPDATE users SET handle = ? WHERE id = ?", (cand, u["id"]))
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_handle ON users(handle COLLATE NOCASE) WHERE handle IS NOT NULL")
        conn.execute("UPDATE users SET email = username WHERE email = '' AND instr(username, '@') > 0")
        _ensure_column(conn, "evidence", "title", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "evidence", "description", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "evidence", "updated_at", "TEXT")
        _ensure_column(conn, "evidence", "updated_by", "INTEGER")
        _ensure_column(conn, "evidence", "deleted_at", "TEXT")
        _ensure_column(conn, "evidence", "deleted_by", "INTEGER")
        _ensure_column(conn, "evidence", "purged_at", "TEXT")
        _ensure_column(conn, "evidence", "last_verified_at", "TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_case ON evidence(case_id, deleted_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_sha ON evidence(sha256)")
        # Databases created before full_name existed: give the bootstrap
        # admin its display name (other users keep showing their username
        # until an admin recreates them with a name).
        conn.execute(
            "UPDATE users SET full_name = ? WHERE username = ? AND full_name = ''",
            (config.DEFAULT_ADMIN_FULL_NAME, config.DEFAULT_ADMIN_USERNAME),
        )
        conn.commit()

        cur = conn.execute("SELECT COUNT(*) AS c FROM users")
        count = cur.fetchone()["c"]
        print(f"[ATHAR] init_db: found {count} existing user(s) in the database")
        if count == 0:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)
            conn.execute(
                "INSERT INTO users (username, full_name, password_hash, role, created_at, email_verified) "
                "VALUES (?, ?, ?, 'ADMIN', ?, 1)",
                (
                    config.DEFAULT_ADMIN_USERNAME,
                    config.DEFAULT_ADMIN_FULL_NAME,
                    security.hash_password(config.DEFAULT_ADMIN_PASSWORD),
                    now,
                ),
            )
            conn.commit()
            print(f"[ATHAR] Created default admin user: '{config.DEFAULT_ADMIN_USERNAME}'")
