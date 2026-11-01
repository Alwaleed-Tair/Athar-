import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import analysis, audit, chats, config, i18n, integrity, relations, textindex
from ..database import get_conn
from ..deps import can_manage_evidence, get_current_user, require_case_member

router = APIRouter(prefix="/api", tags=["evidence"])

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".bmp", ".heic", ".heif"}
CHUNK_SIZE = 1024 * 1024  # 1 MiB


def _now() -> str:
    return datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)


def build_evidence_ai_items(conn, case_id: int) -> list[dict]:
    """
    Every (non-deleted) evidence item of a case as the common payload shared
    by the evidence map and the case summary: id, filename, sha256, upload
    DATE (not a precise time: it reflects the investigator's workflow, not
    the evidence), capture_time (EXIF DateTime -- the real forensic timing
    signal), device, category, user title/description, and -- where
    available -- content_excerpt (text/PDF/Word) or visual_description
    (images, via the vision model). Evidence text is untrusted; the AI
    layer wraps it as inert data (analysis.untrusted_block).
    """
    rows = conn.execute(
        "SELECT id, filename, title, description, stored_name, sha256, uploaded_at, exif_json, category "
        "FROM evidence WHERE case_id = ? AND deleted_at IS NULL ORDER BY uploaded_at ASC",
        (case_id,),
    ).fetchall()

    auth_rows = conn.execute(
        "SELECT evidence_id, result_json FROM evidence_authenticity WHERE evidence_id IN "
        "(SELECT id FROM evidence WHERE case_id = ? AND deleted_at IS NULL)",
        (case_id,),
    ).fetchall()
    auth_by_evidence_id = {}
    for a in auth_rows:
        try:
            result = json.loads(a["result_json"])
            assessment = result.get("ai_assessment")
            if assessment and assessment.get("label"):
                auth_by_evidence_id[a["evidence_id"]] = {
                    "label": assessment["label"],
                    "explanation": assessment.get("explanation", ""),
                }
        except Exception:
            pass

    items = []
    for r in rows:
        try:
            exif = json.loads(r["exif_json"])
        except Exception:
            exif = {}
        make, model = exif.get("Make"), exif.get("Model")
        device = f"{make or ''} {model or ''}".strip() or None

        item = {
            "id": r["id"],
            "filename": r["filename"],
            "title": r["title"] or None,
            "description": (r["description"] or None),
            "sha256": r["sha256"],
            "uploaded_at": (r["uploaded_at"] or "")[:10],
            "capture_time": exif.get("DateTime"),
            "device": device,
            "category": r["category"],
        }
        if r["id"] in auth_by_evidence_id:
            item["authenticity_check"] = auth_by_evidence_id[r["id"]]

        ext = Path(r["filename"]).suffix
        file_path = config.EVIDENCE_DIR / r["stored_name"]
        if file_path.exists():
            excerpt = analysis.extract_text_excerpt(str(file_path), ext)
            if excerpt:
                item["content_excerpt"] = excerpt
            elif ext.lower() in IMAGE_EXTENSIONS:
                description = analysis.describe_image(str(file_path), ext)
                if description:
                    item["visual_description"] = description

        items.append(item)

    return items


@router.get("/cases/{case_id}/cross-case-alerts")
def cross_case_alerts(case_id: int, user: dict = Depends(require_case_member)):
    """
    Links between evidence of THIS case and evidence of OTHER cases that the
    current user is ALSO a member of (identical file, same device, shared
    phone/e-mail/IBAN/URL, shared chat participant, lexical text similarity).
    Cases the user cannot open are never read or hinted at: there is no
    "hidden" alert, so this endpoint cannot be used to probe other users'
    data.
    """
    with get_conn() as conn:
        rels = relations.compute_relations(conn, user["id"], case_id, only_other_cases=True)
    alerts = []
    for r in rels:
        types = [x["type"] for x in r["reasons"]]
        kind = "IDENTICAL_FILE" if "IDENTICAL_FILE" in types else "SAME_DEVICE" if "SAME_DEVICE" in types else "SHARED_CONTENT"
        alerts.append({
            "type": kind,
            "evidence_id": r["evidence_id"],
            "evidence_filename": r["evidence_name"],
            "visible": True,
            "other_case_id": r["other_case_id"],
            "other_case_name": r["other_case_name"],
            "other_evidence_id": r["other_evidence_id"],
            "other_evidence_filename": r["other_evidence_name"],
            "reasons": r["reasons"],
        })
    return {"alerts": alerts}


@router.get("/cases/{case_id}/related")
def related_evidence(case_id: int, user: dict = Depends(require_case_member)):
    """Relations inside this case and to the user's other cases, each with
    the concrete reasons (shared values) behind it."""
    with get_conn() as conn:
        return {"relations": relations.compute_relations(conn, user["id"], case_id)}


@router.get("/cases/{case_id}/evidence-map")
def evidence_map(case_id: int, user: dict = Depends(require_case_member), lang: str = Query(default="en")):
    """
    Correlation graph for a case's evidence, combining two different
    kinds of edges:
    - Deterministic facts, no AI, no threshold: IDENTICAL_FILE (exact
      SHA-256 match) and SAME_DEVICE (exact EXIF Make/Model match).
    - AI-judged relationships (only when ATHAR_AI_KEY is configured):
      the model is given every item's metadata at once and reasons about
      which relationships are genuinely investigatively meaningful --
      there is deliberately NO fixed numeric cutoff (e.g. "within N
      minutes") anywhere in this endpoint. With no AI key, no time-based
      or contextual edges are produced at all; we never substitute a
      guessed threshold for real judgment.
    """
    with get_conn() as conn:
        ai_items = build_evidence_ai_items(conn, case_id)

    nodes = [
        {
            "id": i["id"],
            "filename": i["filename"],
            "sha256": i["sha256"],
            "uploaded_at": i["uploaded_at"],
            "title": i.get("title") or "",
            "device": i["device"],
        }
        for i in ai_items
    ]

    edges = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            a, b = nodes[i], nodes[j]
            if a["sha256"] == b["sha256"]:
                edges.append(
                    {"source": a["id"], "target": b["id"], "type": "IDENTICAL_FILE", "ai_estimated": False}
                )
                continue
            if a["device"] and b["device"] and a["device"] == b["device"]:
                edges.append(
                    {"source": a["id"], "target": b["id"], "type": "SAME_DEVICE", "ai_estimated": False}
                )

    ai_status = None
    ai_message = None
    if len(nodes) >= 2:
        if analysis.ai_enabled():
            # nodes (built above, for the frontend) already captured
            # uploaded_at for display -- strip it from this copy before
            # it reaches the model, since testing showed the model would
            # use upload-time proximity as a "correlation" signal even
            # when explicitly told not to, whenever the field was simply
            # present in the data at all.
            ai_items_for_correlation = [
                {k: v for k, v in item.items() if k != "uploaded_at"} for item in ai_items
            ]
            ai_result = analysis.analyze_case_correlations(ai_items_for_correlation, lang=lang)
            ai_status = ai_result["status"]
            if ai_status == "SUCCESS":
                edges.extend(ai_result["edges"])
            else:
                ai_message = ai_result.get("message_ar" if lang == "ar" else "message_en")
        else:
            ai_status = "DISABLED"
            ai_message = (
                "تحليل الذكاء الاصطناعي معطّل: لم يتم ضبط ATHAR_AI_KEY."
                if lang == "ar"
                else "AI analysis is disabled: no ATHAR_AI_KEY configured."
            )

    return {"nodes": nodes, "edges": edges, "ai_status": ai_status, "ai_message": ai_message}




def _row_evidence_dict(r) -> dict:
    d = dict(r)
    try:
        d["exif"] = json.loads(d.pop("exif_json"))
    except Exception:
        d["exif"] = {}
        d.pop("exif_json", None)
    return d


def _finalize_upload(case_id, user, dest_path, ext, original_name, stored_name, total_bytes, content_type,
                     category, title, description, sha256_hex) -> dict:
    """EXIF, DB insert, audit, text extraction and chat parsing. CPU/IO heavy
    (PDF parsing can take seconds), so it runs in a worker thread, never on the
    server's event loop."""
    if ext in IMAGE_EXTENSIONS:
        exif_status, exif_data = analysis.extract_exif(str(dest_path))
    else:
        exif_status, exif_data = "NOT_APPLICABLE", {}

    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO evidence "
            "(case_id, filename, stored_name, sha256, size_bytes, content_type, "
            " uploaded_by, uploaded_at, exif_status, exif_json, category, title, description, last_verified_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                case_id,
                original_name,
                stored_name,
                sha256_hex,
                total_bytes,
                (content_type or "")[:100],
                user["id"],
                now,
                exif_status,
                json.dumps(exif_data, ensure_ascii=False),
                category,
                title,
                description,
                now,
            ),
        )
        conn.commit()
        evidence_id = cur.lastrowid

    audit.append_event(
        "EVIDENCE_UPLOADED",
        actor_id=user["id"],
        case_id=case_id,
        evidence_id=evidence_id,
        params={
            "username": user["username"],
            "filename": original_name,
            "sha256_short": sha256_hex[:12],
            "sha256": sha256_hex,
            "size_bytes": total_bytes,
        },
    )

    # Content extraction (read-only on the stored original). A parsing
    # problem must never make the upload itself fail.
    conversation = None
    try:
        with get_conn() as conn:
            ev_row = conn.execute("SELECT * FROM evidence WHERE id = ?", (evidence_id,)).fetchone()
            textindex.ensure_text(conn, ev_row)
            parsed = chats.parse_conversation(str(dest_path), ext)
            if parsed:
                chats.store_conversation(conn, evidence_id, parsed)
                conversation = {"format": parsed["format"], "message_count": len(parsed["messages"])}
        if conversation:
            audit.append_event(
                "EVIDENCE_CONVERSATION_PARSED", actor_id=user["id"], case_id=case_id, evidence_id=evidence_id,
                params={"filename": original_name, "count": conversation["message_count"],
                        "format": conversation["format"]},
            )
    except Exception as exc:
        print(f"[ATHAR] content extraction skipped for evidence {evidence_id}: {type(exc).__name__}")

    return {
        "id": evidence_id,
        "filename": original_name,
        "sha256": sha256_hex,
        "size_bytes": total_bytes,
        "exif_status": exif_status,
        "category": category,
        "conversation": conversation,
    }




@router.post("/cases/{case_id}/evidence", status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    case_id: int,
    file: UploadFile = File(...),
    category: str = Form(default=config.DEFAULT_EVIDENCE_CATEGORY),
    title: str = Form(default=""),
    description: str = Form(default=""),
    user: dict = Depends(require_case_member),
):
    if category not in config.EVIDENCE_CATEGORIES:
        category = config.DEFAULT_EVIDENCE_CATEGORY
    title = " ".join(title.split())[:200]
    description = description.strip()[:2000]

    original_name = integrity.sanitize_filename(file.filename or "unnamed")
    ext = Path(original_name).suffix.lower()

    if ext in config.BLOCKED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not allowed for evidence upload.",
        )

    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest_path = config.EVIDENCE_DIR / stored_name

    hasher = hashlib.sha256()
    total_bytes = 0
    first = True
    try:
        with open(dest_path, "wb") as out_f:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                if first:
                    first = False
                    if not integrity.content_matches_extension(ext, chunk[:16]):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="The file content does not match its extension (or is an executable).",
                        )
                total_bytes += len(chunk)
                if total_bytes > config.MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds max upload size of {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                    )
                hasher.update(chunk)
                out_f.write(chunk)
        if total_bytes == 0:
            raise HTTPException(status_code=400, detail="The file is empty.")
    except Exception:
        try:
            os.remove(dest_path)
        except OSError:
            pass
        raise
    finally:
        await file.close()
    try:
        os.chmod(dest_path, 0o600)
    except OSError:
        pass

    sha256_hex = hasher.hexdigest()
    return await run_in_threadpool(
        _finalize_upload, case_id, user, dest_path, ext, original_name, stored_name, total_bytes,
        file.content_type, category, title, description, sha256_hex,
    )


@router.get("/cases/{case_id}/evidence")
def list_evidence(case_id: int, user: dict = Depends(require_case_member)):
    with get_conn() as conn:
        case_row = conn.execute("SELECT created_by FROM cases WHERE id = ?", (case_id,)).fetchone()
        rows = conn.execute(
            "SELECT e.id, e.case_id, e.filename, e.title, e.description, e.sha256, e.size_bytes, e.content_type, "
            "e.uploaded_by, e.uploaded_at, e.updated_at, e.exif_status, e.category, e.last_verified_at, "
            "COALESCE(NULLIF(u.full_name, ''), u.username) AS uploader_name, "
            "(SELECT message_count FROM conversations c WHERE c.evidence_id = e.id) AS message_count "
            "FROM evidence e JOIN users u ON u.id = e.uploaded_by "
            "WHERE e.case_id = ? AND e.deleted_at IS NULL ORDER BY e.uploaded_at DESC",
            (case_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["can_manage"] = user["id"] == r["uploaded_by"] or user["id"] == case_row["created_by"]
        out.append(d)
    return out


def _load_evidence(evidence_id: int, user: dict, require_manage: bool = False):
    """Loads a NON-deleted evidence row for a member of its case. Missing,
    deleted, or not-a-member all look identical (404). `require_manage`
    additionally demands uploader/case-owner rights (403: the user can
    already see the case, so there is nothing to hide)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM evidence WHERE id = ? AND deleted_at IS NULL", (evidence_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Evidence not found")
        member_row = conn.execute(
            "SELECT 1 FROM case_members WHERE case_id = ? AND user_id = ?",
            (row["case_id"], user["id"]),
        ).fetchone()
        case_row = conn.execute("SELECT * FROM cases WHERE id = ?", (row["case_id"],)).fetchone()
        if not member_row or not case_row or case_row["status"] == "DELETED":
            raise HTTPException(status_code=404, detail="Evidence not found")
    if require_manage and not can_manage_evidence(user, row, case_row):
        raise HTTPException(status_code=403, detail="NOT_ALLOWED")
    return _row_evidence_dict(row), case_row


def _get_evidence_or_404(evidence_id: int, user: dict) -> dict:  # kept for older call sites
    return _load_evidence(evidence_id, user)[0]


def _require_intact(ev: dict, user: dict) -> str:
    """Refuses to process a file that no longer matches its recorded hash.
    Returns the verified sha256."""
    result, actual = integrity.check_file(ev)
    if result != "MATCH":
        integrity.record_check(ev, user, result)
        raise HTTPException(status_code=409, detail="INTEGRITY_FAILURE")
    return actual


class UpdateEvidenceRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    category: Optional[str] = None


@router.patch("/evidence/{evidence_id}")
def update_evidence(evidence_id: int, body: UpdateEvidenceRequest, user: dict = Depends(get_current_user)):
    """Edits METADATA only (title, description, category). The stored file
    and its SHA-256 are never touched; every change is audit-logged with
    old and new values."""
    ev, _case = _load_evidence(evidence_id, user, require_manage=True)
    changes, sets, vals = {}, [], []
    if body.title is not None:
        new = " ".join(body.title.split())
        if new != (ev["title"] or ""):
            changes["title"] = [ev["title"] or "", new]
            sets.append("title = ?"); vals.append(new)
    if body.description is not None:
        new = body.description.strip()
        if new != (ev["description"] or ""):
            changes["description"] = [ev["description"] or "", new]
            sets.append("description = ?"); vals.append(new)
    if body.category is not None:
        if body.category not in config.EVIDENCE_CATEGORIES:
            raise HTTPException(status_code=400, detail="Invalid category")
        if body.category != ev["category"]:
            changes["category"] = [ev["category"], body.category]
            sets.append("category = ?"); vals.append(body.category)
    if not changes:
        return {"id": evidence_id, "changed": []}

    now = _now()
    with get_conn() as conn:
        conn.execute(
            f"UPDATE evidence SET {', '.join(sets)}, updated_at = ?, updated_by = ? WHERE id = ?",
            (*vals, now, user["id"], evidence_id),
        )
        # titles/descriptions feed AI correlations and the summary -> refresh on demand
        conn.execute("DELETE FROM case_summary WHERE case_id = ?", (ev["case_id"],))
        conn.commit()
    audit.append_event(
        "EVIDENCE_UPDATED", actor_id=user["id"], case_id=ev["case_id"], evidence_id=evidence_id,
        params={"username": user["username"], "filename": ev["filename"],
                "fields": ", ".join(changes), "changes": changes},
    )
    return {"id": evidence_id, "changed": list(changes)}


@router.delete("/evidence/{evidence_id}")
def delete_evidence(evidence_id: int, user: dict = Depends(get_current_user)):
    """Soft delete per the retention policy: the item disappears from every
    list, map, search and report at once, derived data (text, parsed chat,
    AI results) is removed, and the stored file + hash are kept for
    ATHAR_EVIDENCE_RETENTION_DAYS before being purged. The audit log is never
    altered."""
    ev, _case = _load_evidence(evidence_id, user, require_manage=True)
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "UPDATE evidence SET deleted_at = ?, deleted_by = ? WHERE id = ?", (now, user["id"], evidence_id)
        )
        integrity.delete_derived_data(conn, evidence_id, ev["case_id"])
        conn.commit()
    purge_after = integrity.purge_after(now)
    audit.append_event(
        "EVIDENCE_DELETED", actor_id=user["id"], case_id=ev["case_id"], evidence_id=evidence_id,
        params={"username": user["username"], "filename": ev["filename"],
                "sha256_short": ev["sha256"][:12], "sha256": ev["sha256"], "purge_after": purge_after},
    )
    integrity.purge_expired()
    return {"id": evidence_id, "status": "DELETED", "purge_after": purge_after}


class SetCategoryRequest(BaseModel):
    category: str


@router.patch("/evidence/{evidence_id}/category")
def set_evidence_category(
    evidence_id: int, body: SetCategoryRequest, user: dict = Depends(get_current_user)
):
    return update_evidence(evidence_id, UpdateEvidenceRequest(category=body.category), user)


@router.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: int, user: dict = Depends(get_current_user), lang: str = Query(default="en")):
    ev, case_row = _load_evidence(evidence_id, user)
    ev["can_manage"] = can_manage_evidence(user, ev, case_row)

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE evidence_id = ? ORDER BY seq ASC", (evidence_id,)
        ).fetchall()
        conv = chats.get_meta(conn, evidence_id)
        uploader = conn.execute(
            "SELECT COALESCE(NULLIF(full_name, ''), username) AS n FROM users WHERE id = ?", (ev["uploaded_by"],)
        ).fetchone()
    ev["uploader_name"] = uploader["n"] if uploader else ""
    ev["conversation"] = (
        {k: conv[k] for k in ("format", "message_count", "first_ts", "last_ts")} if conv else None
    )
    ev.pop("stored_name", None)
    with get_conn() as conn:
        t = conn.execute("SELECT text, source, extracted_at FROM evidence_text WHERE evidence_id = ?", (evidence_id,)).fetchone()
    ev["ocr"] = ({"method": t["source"], "text": t["text"][:6000], "extracted_at": t["extracted_at"]}
                 if t and t["source"].startswith("OCR_") else None)
    custody_log = []
    for r in rows:
        try:
            params = json.loads(r["params_json"])
        except Exception:
            params = {}
        custody_log.append(
            {
                "seq": r["seq"],
                "action": r["action"],
                "ts": r["ts"],
                "event_hash": r["event_hash"],
                "message": i18n.build_message(r["action"], params, lang),
            }
        )
    ev["custody_log"] = custody_log

    with get_conn() as conn:
        cached = conn.execute(
            "SELECT result_json, lang, analyzed_at FROM evidence_analysis WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchone()
        cached_auth = conn.execute(
            "SELECT result_json, lang, checked_at FROM evidence_authenticity WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchone()
    if cached:
        try:
            ev["cached_analysis"] = json.loads(cached["result_json"])
            ev["cached_analysis_lang"] = cached["lang"]
            ev["cached_analysis_at"] = cached["analyzed_at"]
        except Exception:
            pass
    if cached_auth:
        try:
            ev["cached_authenticity"] = json.loads(cached_auth["result_json"])
            ev["cached_authenticity_lang"] = cached_auth["lang"]
            ev["cached_authenticity_at"] = cached_auth["checked_at"]
        except Exception:
            pass

    audit.append_event(
        "EVIDENCE_OPENED",
        actor_id=user["id"],
        case_id=ev["case_id"],
        evidence_id=evidence_id,
        params={"username": user["username"], "filename": ev["filename"]},
    )
    return ev


@router.post("/evidence/{evidence_id}/verify-integrity")
def verify_integrity(evidence_id: int, user: dict = Depends(get_current_user)):
    """Re-hashes the stored file and compares with the SHA-256 recorded at upload."""
    ev, _case = _load_evidence(evidence_id, user)
    result, actual = integrity.check_file(ev)
    integrity.record_check(ev, user, result)
    return {
        "result": result,
        "intact": result == "MATCH",
        "expected_sha256": ev["sha256"],
        "actual_sha256": actual,
        "checked_at": _now(),
    }


@router.get("/evidence/{evidence_id}/download")
def download_evidence(evidence_id: int, user: dict = Depends(get_current_user)):
    ev, _case = _load_evidence(evidence_id, user)
    file_path = config.EVIDENCE_DIR / ev["stored_name"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Stored file missing on disk")
    # Never hand out a file that no longer matches its recorded hash.
    _require_intact(ev, user)

    audit.append_event(
        "EVIDENCE_DOWNLOADED",
        actor_id=user["id"],
        case_id=ev["case_id"],
        evidence_id=evidence_id,
        params={"username": user["username"], "filename": ev["filename"]},
    )
    return FileResponse(
        path=str(file_path),
        filename=ev["filename"],
        media_type="application/octet-stream",
        headers={"X-Content-Type-Options": "nosniff", "X-Evidence-SHA256": ev["sha256"]},
    )


@router.post("/evidence/{evidence_id}/analyze")
def analyze_evidence(evidence_id: int, user: dict = Depends(get_current_user), lang: str = Query(default="en")):
    ev, _case = _load_evidence(evidence_id, user)
    hash_before = _require_intact(ev, user)

    with get_conn() as conn:
        other_rows = conn.execute(
            "SELECT filename, title, description, stored_name, sha256, size_bytes, uploaded_at, exif_json FROM evidence "
            "WHERE case_id = ? AND id != ? AND deleted_at IS NULL",
            (ev["case_id"], evidence_id),
        ).fetchall()

    def with_content_excerpt(d: dict) -> dict:
        stored_name = d.pop("stored_name", None)
        if stored_name:
            file_path = config.EVIDENCE_DIR / stored_name
            if file_path.exists():
                ext = Path(d["filename"]).suffix
                excerpt = analysis.extract_text_excerpt(str(file_path), ext)
                if excerpt:
                    d["content_excerpt"] = excerpt
                elif ext.lower() in IMAGE_EXTENSIONS:
                    description = analysis.describe_image(str(file_path), ext)
                    if description:
                        d["visual_description"] = description
        return d

    related = []
    for r in other_rows:
        d = dict(r)
        try:
            d["exif"] = json.loads(d.pop("exif_json"))
        except Exception:
            d["exif"] = {}
        d.pop("uploaded_at", None)  # administrative artefact, not forensic evidence
        related.append(with_content_excerpt(d))

    target = with_content_excerpt(
        {
            "filename": ev["filename"],
            "title": ev["title"],
            "description": ev["description"],
            "stored_name": ev["stored_name"],
            "sha256": ev["sha256"],
            "exif": ev["exif"],
        }
    )

    result = analysis.analyze_evidence(target, related, lang=lang)

    # Second hash after processing: proves the original was not altered.
    hash_after = integrity.file_sha256(config.EVIDENCE_DIR / ev["stored_name"])
    if hash_after != hash_before:
        integrity.record_check(ev, user, "MISMATCH")
        raise HTTPException(status_code=409, detail="INTEGRITY_FAILURE")

    if result.get("status") == "SUCCESS":
        now = _now()
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO evidence_analysis (evidence_id, result_json, lang, analyzed_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(evidence_id) DO UPDATE SET "
                "result_json = excluded.result_json, lang = excluded.lang, analyzed_at = excluded.analyzed_at",
                (evidence_id, json.dumps(result, ensure_ascii=False), lang, now),
            )
            conn.commit()

    audit.append_event(
        "EVIDENCE_ANALYZED",
        actor_id=user["id"],
        case_id=ev["case_id"],
        evidence_id=evidence_id,
        params={"username": user["username"], "filename": ev["filename"],
                "sha256_before": hash_before, "sha256_after": hash_after, "ai_status": result.get("status")},
    )
    return result


@router.post("/evidence/{evidence_id}/ocr")
def run_ocr(evidence_id: int, user: dict = Depends(get_current_user)):
    """User-triggered text extraction from an image/screenshot (the image is
    only read, never modified). If the text looks like a chat it is also
    parsed into messages. Output is an approximation and labelled as such."""
    ev, _case = _load_evidence(evidence_id, user)
    if Path(ev["filename"]).suffix.lower() not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="NOT_AN_IMAGE")
    hash_before = _require_intact(ev, user)
    result = analysis.ocr_image(str(config.EVIDENCE_DIR / ev["stored_name"]))
    if integrity.file_sha256(config.EVIDENCE_DIR / ev["stored_name"]) != hash_before:
        raise HTTPException(status_code=409, detail="INTEGRITY_FAILURE")
    conversation = None
    if result["status"] == "SUCCESS":
        source = "OCR_" + result["method"]
        with get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO evidence_text (evidence_id, text, extracted_at, source) VALUES (?,?,?,?)",
                         (evidence_id, result["text"], _now(), source))
            conn.execute("DELETE FROM case_summary WHERE case_id = ?", (ev["case_id"],))
            lines = [(f"ocr line {i}", ln) for i, ln in enumerate(result["text"].splitlines(), start=1)]
            parsed = chats.parse_timestamped_lines(lines) or chats.parse_speaker_lines(lines)
            if parsed:
                parsed["format"] = "OCR_TEXT"
                parsed["participants"] = [{"name": n, "messages": c} for n, c in
                                          __import__("collections").Counter(m["sender"] for m in parsed["messages"] if m["sender"]).most_common()]
                chats.store_conversation(conn, evidence_id, parsed)
                conversation = {"format": "OCR_TEXT", "message_count": len(parsed["messages"])}
            conn.commit()
    audit.append_event(
        "EVIDENCE_OCR_RUN", actor_id=user["id"], case_id=ev["case_id"], evidence_id=evidence_id,
        params={"username": user["username"], "filename": ev["filename"], "method": result.get("method") or "NONE",
                "status": result["status"], "sha256_before": hash_before, "sha256_after": hash_before},
    )
    result["conversation"] = conversation
    result["is_approximation"] = True
    return result


# --- Conversations -----------------------------------------------------------------

def _conversation_or_404(evidence_id: int, user: dict):
    ev, case_row = _load_evidence(evidence_id, user)
    with get_conn() as conn:
        meta = chats.get_meta(conn, evidence_id)
    if not meta:
        raise HTTPException(status_code=404, detail="NOT_A_CONVERSATION")
    return ev, case_row, meta


@router.get("/evidence/{evidence_id}/conversation")
def get_conversation(
    evidence_id: int,
    q: str = Query(default="", max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    """Parsed conversation: participants, date range, statistics, messages
    (or only the messages matching `q`), plus deterministic links to other
    evidence in the same case. Each message carries `source_ref` pointing
    to its exact location in the original file."""
    ev, _case, meta = _conversation_or_404(evidence_id, user)
    with get_conn() as conn:
        stats = chats.compute_stats(conn, evidence_id)
        if q.strip():
            msgs = chats.search_messages(conn, evidence_id, q)
            matched = True
        else:
            msgs = chats.get_messages(conn, evidence_id, offset, limit)
            matched = False
        links = chats.link_to_evidence(conn, evidence_id, ev["case_id"])
    return {
        "meta": meta, "stats": stats, "messages": msgs, "query": q.strip(), "is_search": matched,
        "offset": offset, "limit": limit, "links": links,
        "notes": {
            "untrusted": True,
            "time_zone_unknown": True,
            "date_order_assumed": meta["format"] in ("TEXT_TIMESTAMPED", "PDF_TEXT", "DOCX_TEXT"),
        },
    }


@router.post("/evidence/{evidence_id}/conversation/summary")
def summarize_conversation(evidence_id: int, user: dict = Depends(get_current_user), lang: str = Query(default="en")):
    ev, _case, meta = _conversation_or_404(evidence_id, user)
    _require_intact(ev, user)
    with get_conn() as conn:
        total = meta["message_count"]
        rows = [dict(r) for r in conn.execute(
            "SELECT idx, sender, ts, body FROM chat_messages WHERE evidence_id = ? ORDER BY idx", (evidence_id,))]
    if total > 400:  # head + tail + evenly spaced middle
        step = max(1, (total - 300) // 100)
        keep = set(range(0, 150)) | set(range(total - 150, total)) | set(range(150, total - 150, step))
        sample = [rows[i] for i in sorted(keep) if i < len(rows)]
    else:
        sample = rows
    result = analysis.summarize_conversation(meta, sample, total, lang=lang)
    if result.get("status") == "SUCCESS":
        result["lang"] = lang
        result["generated_at"] = _now()
        with get_conn() as conn:
            conn.execute("UPDATE conversations SET summary_json = ? WHERE evidence_id = ?",
                         (json.dumps(result, ensure_ascii=False), evidence_id))
            conn.commit()
    audit.append_event(
        "CONVERSATION_SUMMARY_GENERATED", actor_id=user["id"], case_id=ev["case_id"], evidence_id=evidence_id,
        params={"username": user["username"], "filename": ev["filename"], "ai_status": result.get("status")},
    )
    return result


@router.post("/evidence/{evidence_id}/authenticity-check")
def check_evidence_authenticity(
    evidence_id: int, user: dict = Depends(get_current_user), lang: str = Query(default="en")
):
    """
    Runs (and caches) an approximate authenticity check for an image:
    deterministic EXIF indicators (always computed, no AI) plus a
    rough, low-confidence AI visual triage for common manipulation
    artifacts (only if ATHAR_AI_KEY is set). This is explicitly NOT a
    reliable deepfake-detection tool -- see assess_image_authenticity's
    docstring -- and the frontend must present it as a rough hint only.
    """
    ev, _case = _load_evidence(evidence_id, user)
    ext = Path(ev["filename"]).suffix.lower()

    if ext not in IMAGE_EXTENSIONS:
        return {"status": "NOT_APPLICABLE"}

    exif_indicators = analysis.check_exif_authenticity_indicators(ev.get("exif") or {})

    _require_intact(ev, user)
    file_path = config.EVIDENCE_DIR / ev["stored_name"]
    if not file_path.exists():
        ai_result = {
            "status": "FAILED",
            "message_en": "Stored file missing on disk.",
            "message_ar": "الملف المخزّن غير موجود على القرص.",
        }
    else:
        ai_result = analysis.assess_image_authenticity(str(file_path), lang=lang)

    result = {
        "status": ai_result["status"],
        "exif_indicators": exif_indicators,
        "ai_assessment": ai_result if ai_result["status"] == "SUCCESS" else None,
        "ai_status": ai_result["status"],
        "ai_message": ai_result.get("message_ar" if lang == "ar" else "message_en"),
    }

    now = datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO evidence_authenticity (evidence_id, result_json, lang, checked_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(evidence_id) DO UPDATE SET "
            "result_json = excluded.result_json, lang = excluded.lang, checked_at = excluded.checked_at",
            (evidence_id, json.dumps(result, ensure_ascii=False), lang, now),
        )
        conn.commit()

    audit.append_event(
        "EVIDENCE_AUTHENTICITY_CHECKED",
        actor_id=user["id"],
        case_id=ev["case_id"],
        evidence_id=evidence_id,
        params={"username": user["username"], "filename": ev["filename"]},
    )
    return result