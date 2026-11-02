"""
File integrity + upload hygiene + retention for evidence files.

Principles:
* The stored original is NEVER modified. Every derived artefact (EXIF,
  extracted text, parsed conversation, AI output) is computed from it
  read-only and stored separately.
* The SHA-256 recorded at upload is the reference. Before any processing
  step we re-hash the file on disk and compare; processing is refused if
  the file no longer matches. For AI analysis we hash again afterwards
  and record both values in the audit log.
"""
import hashlib
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from . import audit, config
from .database import get_conn

CHUNK = 1024 * 1024


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def check_file(ev_row) -> tuple[str, Optional[str]]:
    """Re-hash the stored file. Returns (MATCH|MISMATCH|MISSING, actual_hash)."""
    path = config.EVIDENCE_DIR / ev_row["stored_name"]
    if not path.exists():
        return "MISSING", None
    actual = file_sha256(path)
    return ("MATCH" if actual == ev_row["sha256"] else "MISMATCH"), actual


def record_check(ev_row, user: dict, result: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE evidence SET last_verified_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT), ev_row["id"]),
        )
        conn.commit()
    audit.append_event(
        "EVIDENCE_INTEGRITY_CHECKED",
        actor_id=user["id"],
        case_id=ev_row["case_id"],
        evidence_id=ev_row["id"],
        params={"username": user["username"], "filename": ev_row["filename"], "result": result},
    )


# --- upload hygiene -------------------------------------------------------

def sanitize_filename(name: str) -> str:
    """Keeps the visible name but removes path separators, control and
    bidi-override characters (used to disguise extensions), and caps length."""
    name = unicodedata.normalize("NFC", name or "unnamed")
    name = name.replace("\\", "/").split("/")[-1]
    name = "".join(
        ch for ch in name
        if unicodedata.category(ch) not in ("Cc", "Cf") or ch in ("‌", "‍")
    )
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    if not name:
        name = "unnamed"
    if len(name) > 180:
        stem, dot, ext = name.rpartition(".")
        name = (stem[:170] + dot + ext[:8]) if dot else name[:180]
    return name


_SIGNATURES = {
    ".pdf": [b"%PDF-"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".gif": [b"GIF87a", b"GIF89a"],
    ".bmp": [b"BM"],
    ".webp": [b"RIFF"],
    ".docx": [b"PK\x03\x04"],
    ".xlsx": [b"PK\x03\x04"],
    ".zip": [b"PK\x03\x04"],
    ".tif": [b"II*\x00", b"MM\x00*"],
    ".tiff": [b"II*\x00", b"MM\x00*"],
}
_EXECUTABLE_MAGIC = [b"MZ", b"\x7fELF", b"\xca\xfe\xba\xbe", b"#!"]


def content_matches_extension(ext: str, head: bytes) -> bool:
    """Light magic-byte check: a file named .pdf/.png/... must start like one,
    and no file may start like a Windows/Linux executable or a script."""
    if any(head.startswith(m) for m in _EXECUTABLE_MAGIC):
        return False
    sigs = _SIGNATURES.get(ext.lower())
    if sigs is None:
        return True  # unknown/plain types (txt, csv, json, heic...) are accepted
    return any(head.startswith(s) for s in sigs)


# --- retention ------------------------------------------------------------

def purge_after(deleted_at: str) -> str:
    try:
        dt = datetime.strptime(deleted_at, config.TIMESTAMP_FORMAT)
    except ValueError:
        dt = datetime.now(timezone.utc).replace(tzinfo=None)
    return (dt + timedelta(days=config.EVIDENCE_RETENTION_DAYS)).strftime("%Y-%m-%d")


def purge_expired() -> int:
    """Permanently remove stored files of soft-deleted evidence whose
    retention period has ended. The evidence row and audit trail stay."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=config.EVIDENCE_RETENTION_DAYS)).strftime(
        config.TIMESTAMP_FORMAT
    )
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM evidence WHERE deleted_at IS NOT NULL AND purged_at IS NULL AND deleted_at < ?",
            (cutoff,),
        ).fetchall()
    n = 0
    for r in rows:
        try:
            (config.EVIDENCE_DIR / r["stored_name"]).unlink(missing_ok=True)
        except OSError:
            continue
        with get_conn() as conn:
            conn.execute(
                "UPDATE evidence SET purged_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT), r["id"]),
            )
            conn.commit()
        audit.append_event(
            "EVIDENCE_PURGED", actor_id=None, case_id=r["case_id"], evidence_id=r["id"],
            params={"filename": r["filename"], "sha256_short": r["sha256"][:12]},
        )
        n += 1
    return n


def delete_derived_data(conn, evidence_id: int, case_id: int) -> None:
    """Remove everything computed FROM an evidence item, plus cached
    cross-evidence results that may mention it, so nothing stale or
    inconsistent is left behind. The original file row and the audit log
    are untouched."""
    conn.execute("DELETE FROM evidence_analysis WHERE evidence_id = ?", (evidence_id,))
    conn.execute("DELETE FROM evidence_authenticity WHERE evidence_id = ?", (evidence_id,))
    conn.execute("DELETE FROM evidence_text WHERE evidence_id = ?", (evidence_id,))
    conn.execute("DELETE FROM evidence_embeddings WHERE evidence_id = ?", (evidence_id,))
    conn.execute("DELETE FROM chat_messages WHERE evidence_id = ?", (evidence_id,))
    conn.execute("DELETE FROM conversations WHERE evidence_id = ?", (evidence_id,))
    # Other items' AI correlations and the case summary may reference this
    # item -- drop them; they regenerate on demand.
    conn.execute(
        "DELETE FROM evidence_analysis WHERE evidence_id IN (SELECT id FROM evidence WHERE case_id = ?)",
        (case_id,),
    )
    conn.execute("DELETE FROM case_summary WHERE case_id = ?", (case_id,))
    conn.execute("DELETE FROM case_map_ai WHERE case_id = ?", (case_id,))
