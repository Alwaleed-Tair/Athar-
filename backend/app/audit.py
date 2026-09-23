"""
Chain-of-custody audit log.

Every action (login, case opened, evidence uploaded, opened, downloaded,
analyzed) appends one row to audit_log. Each row's event_hash is a SHA-256
over a canonical (sorted-key) JSON document that includes the previous
row's hash, so any tampering with a past row breaks the chain from that
point forward and is detectable by /audit/verify.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from . import config
from .database import AUDIT_LOCK, get_conn

GENESIS_HASH = "0" * 64


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)


def _canonical_payload(
    previous_hash: str,
    seq: int,
    actor_id: Optional[int],
    action: str,
    case_id: Optional[int],
    evidence_id: Optional[int],
    ts: str,
    params: dict,
) -> str:
    doc = {
        "previous_hash": previous_hash,
        "seq": seq,
        "actor_id": actor_id,
        "action": action,
        "case_id": case_id,
        "evidence_id": evidence_id,
        "ts": ts,
        "params": params,
    }
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _compute_hash(*args, **kwargs) -> str:
    payload = _canonical_payload(*args, **kwargs)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append_event(
    action: str,
    actor_id: Optional[int],
    case_id: Optional[int] = None,
    evidence_id: Optional[int] = None,
    params: Optional[dict] = None,
) -> dict:
    """Append one row to the chain. Thread-safe: acquires AUDIT_LOCK and
    re-reads the true last row from the DB *inside* the lock, so concurrent
    requests can never both compute their hash off the same "previous"
    row."""
    params = params or {}
    with AUDIT_LOCK:
        with get_conn() as conn:
            cur = conn.execute(
                "SELECT event_hash FROM audit_log ORDER BY seq DESC LIMIT 1"
            )
            row = cur.fetchone()
            previous_hash = row["event_hash"] if row else GENESIS_HASH

            cur = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM audit_log")
            next_seq = cur.fetchone()["next_seq"]

            ts = _now_str()
            event_hash = _compute_hash(
                previous_hash, next_seq, actor_id, action, case_id, evidence_id, ts, params
            )

            conn.execute(
                "INSERT INTO audit_log "
                "(seq, previous_hash, event_hash, actor_id, action, case_id, evidence_id, ts, params_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    next_seq,
                    previous_hash,
                    event_hash,
                    actor_id,
                    action,
                    case_id,
                    evidence_id,
                    ts,
                    json.dumps(params, sort_keys=True, ensure_ascii=False),
                ),
            )
            conn.commit()

            return {
                "seq": next_seq,
                "previous_hash": previous_hash,
                "event_hash": event_hash,
                "actor_id": actor_id,
                "action": action,
                "case_id": case_id,
                "evidence_id": evidence_id,
                "ts": ts,
                "params": params,
            }


def verify_chain(case_id: Optional[int] = None) -> dict:
    """Recompute every row's hash from its stored fields and compare
    against the stored event_hash AND the linkage to the previous row.
    Returns intact / records_checked / first_broken_seq."""
    with get_conn() as conn:
        if case_id is not None:
            cur = conn.execute(
                "SELECT * FROM audit_log WHERE case_id = ? ORDER BY seq ASC", (case_id,)
            )
        else:
            cur = conn.execute("SELECT * FROM audit_log ORDER BY seq ASC")
        rows = cur.fetchall()

    expected_previous = GENESIS_HASH if case_id is None else None
    records_checked = 0
    first_broken_seq = None

    for row in rows:
        records_checked += 1
        try:
            params = json.loads(row["params_json"])
        except (json.JSONDecodeError, TypeError):
            params = {}

        recomputed = _compute_hash(
            row["previous_hash"],
            row["seq"],
            row["actor_id"],
            row["action"],
            row["case_id"],
            row["evidence_id"],
            row["ts"],
            params,
        )

        broken = recomputed != row["event_hash"]
        if not broken and case_id is None:
            broken = row["previous_hash"] != expected_previous

        if broken and first_broken_seq is None:
            first_broken_seq = row["seq"]

        expected_previous = row["event_hash"]

    return {
        "intact": first_broken_seq is None,
        "records_checked": records_checked,
        "first_broken_seq": first_broken_seq,
    }
