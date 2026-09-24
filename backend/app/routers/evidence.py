import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import analysis, audit, config, i18n
from ..database import get_conn
from ..deps import get_current_user, require_case_member

router = APIRouter(prefix="/api", tags=["evidence"])

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".bmp", ".heic", ".heif"}
CHUNK_SIZE = 1024 * 1024  # 1 MiB


def build_evidence_ai_items(conn, case_id: int) -> list[dict]:
    """
    Returns every evidence item in a case as the common "give the AI
    everything we can extract" payload shared by the evidence map, the
    case summary, and (in spirit) the per-item analysis endpoint: id,
    filename, sha256, uploaded_at, capture_time (the real EXIF capture
    timestamp, when present -- NOT the same as uploaded_at, see below),
    device (from EXIF), category, and -- where available --
    content_excerpt (text/PDF/Word) or visual_description (images, via
    the vision model). Building this once here avoids re-implementing
    the same extraction loop in three places.

    capture_time vs uploaded_at: uploaded_at is when someone added the
    file to THIS system and reflects the investigator's own workflow
    (e.g. uploading a backlog of unrelated files back-to-back), not
    anything about the evidence itself -- it is not a meaningful
    forensic timing signal on its own. capture_time (EXIF DateTime) is
    when the content was actually created/captured and is what genuinely
    matters for timing analysis. Both are included so callers (and the
    AI prompts) can prefer capture_time and treat uploaded_at proximity
    as weak/non-evidence on its own.
    """
    rows = conn.execute(
        "SELECT id, filename, stored_name, sha256, uploaded_at, exif_json, category "
        "FROM evidence WHERE case_id = ? ORDER BY uploaded_at ASC",
        (case_id,),
    ).fetchall()

    auth_rows = conn.execute(
        "SELECT evidence_id, result_json FROM evidence_authenticity WHERE evidence_id IN "
        "(SELECT id FROM evidence WHERE case_id = ?)",
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
            "sha256": r["sha256"],
            "uploaded_at": r["uploaded_at"],
            "capture_time": exif.get("DateTime"),
            "device": device,
            "category": r["category"],
        }
        if r["id"] in auth_by_evidence_id:
            # A rough, low-confidence AI authenticity verdict (REAL /
            # FAKE / UNSURE) from a prior "authenticity check" run on
            # this item, if the investigator ran one. Included so the
            # summary and map can factor it in and flag it -- not to be
            # treated as proven, but it must not be silently ignored
            # either when it's the only thing suggesting an item may not
            # be genuine.
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
    Deterministic (no AI, no threshold) cross-case correlation check:
    flags when evidence in THIS case shares an exact SHA-256 hash or an
    exact EXIF device (Make+Model) with evidence in a DIFFERENT,
    non-deleted case. If the current user isn't a member of that other
    case, the alert is still returned (so they know a link exists) but
    without its case name, evidence filename, or ids -- membership
    isolation applies to what this endpoint reveals, not whether an
    alert appears at all.
    """
    with get_conn() as conn:
        alerts = []

        hash_matches = conn.execute(
            "SELECT r.id AS my_id, r.filename AS my_filename, "
            "o.id AS other_id, o.filename AS other_filename, "
            "o.case_id AS other_case_id, c.name AS other_case_name "
            "FROM evidence r "
            "JOIN evidence o ON o.sha256 = r.sha256 AND o.case_id != r.case_id "
            "JOIN cases c ON c.id = o.case_id AND c.status != 'DELETED' "
            "WHERE r.case_id = ?",
            (case_id,),
        ).fetchall()
        already_matched_pairs = set()
        for m in hash_matches:
            already_matched_pairs.add((m["my_id"], m["other_id"]))
            is_member = (
                conn.execute(
                    "SELECT 1 FROM case_members WHERE case_id = ? AND user_id = ?",
                    (m["other_case_id"], user["id"]),
                ).fetchone()
                is not None
            )
            alerts.append(_build_cross_case_alert("IDENTICAL_FILE", m, is_member))

        def device_of(exif_json: str):
            try:
                exif = json.loads(exif_json)
            except Exception:
                exif = {}
            make, model = exif.get("Make"), exif.get("Model")
            return f"{make or ''} {model or ''}".strip() or None

        my_rows = conn.execute(
            "SELECT id, filename, exif_json FROM evidence WHERE case_id = ?", (case_id,)
        ).fetchall()
        other_rows = conn.execute(
            "SELECT e.id, e.filename, e.exif_json, e.case_id, c.name AS case_name "
            "FROM evidence e JOIN cases c ON c.id = e.case_id "
            "WHERE e.case_id != ? AND c.status != 'DELETED'",
            (case_id,),
        ).fetchall()
        other_by_device: dict = {}
        for o in other_rows:
            d = device_of(o["exif_json"])
            if d:
                other_by_device.setdefault(d, []).append(o)

        for r in my_rows:
            d = device_of(r["exif_json"])
            if not d:
                continue
            for o in other_by_device.get(d, []):
                if (r["id"], o["id"]) in already_matched_pairs:
                    continue
                is_member = (
                    conn.execute(
                        "SELECT 1 FROM case_members WHERE case_id = ? AND user_id = ?",
                        (o["case_id"], user["id"]),
                    ).fetchone()
                    is not None
                )
                alerts.append(
                    _build_cross_case_alert(
                        "SAME_DEVICE",
                        {
                            "my_id": r["id"],
                            "my_filename": r["filename"],
                            "other_id": o["id"],
                            "other_filename": o["filename"],
                            "other_case_id": o["case_id"],
                            "other_case_name": o["case_name"],
                        },
                        is_member,
                    )
                )

        # 3) Content mention (deterministic literal text match, no AI):
        # does a text/PDF/Word file in THIS case literally name another
        # case, literally name a piece of evidence that belongs to
        # another case, or literally describe another case's evidence's
        # EXIF device (e.g. text says "iPhone 14" and another case's
        # photo has that exact EXIF Model)? This is what catches a
        # report saying, e.g., "the victim's iPhone 14" -- the hash and
        # device-to-device checks above only catch identical files or
        # two items that BOTH have matching EXIF; this also catches a
        # device only described in prose on one side.
        # A handful of common device-brand transliterations so an Arabic
        # mention (e.g. "ايفون 14" or "آيفون 14") matches an EXIF Model
        # written in Latin script ("iPhone 14"). This is a small, fixed
        # lookup table, not general translation -- it only covers common
        # phone brands and won't catch every possible spelling.
        BRAND_TRANSLITERATIONS = {
            "iphone": ["ايفون", "آيفون", "أيفون"],
            "apple": ["ابل", "آبل", "أبل"],
            "samsung": ["سامسونج", "سامسونغ"],
            "huawei": ["هواوي"],
            "xiaomi": ["شاومي"],
            "oppo": ["اوبو", "أوبو"],
            "nokia": ["نوكيا"],
        }

        def device_terms(exif_json: str):
            try:
                exif = json.loads(exif_json or "{}")
            except Exception:
                exif = {}
            make, model = exif.get("Make"), exif.get("Model")
            terms = []
            if model:
                model = str(model)
                terms.append(model)
                first_word, _, rest = model.partition(" ")
                for variant in BRAND_TRANSLITERATIONS.get(first_word.lower(), []):
                    terms.append(f"{variant} {rest}".strip())
            if make and model:
                terms.append(f"{make} {model}")
                for variant in BRAND_TRANSLITERATIONS.get(str(make).lower(), []):
                    terms.append(f"{variant} {model}".strip())
            return terms

        other_cases_and_evidence = conn.execute(
            "SELECT c.id AS case_id, c.name AS case_name, "
            "e.id AS evidence_id, e.filename AS evidence_filename, e.exif_json AS evidence_exif_json "
            "FROM cases c LEFT JOIN evidence e ON e.case_id = c.id "
            "WHERE c.id != ? AND c.status != 'DELETED'",
            (case_id,),
        ).fetchall()
        if other_cases_and_evidence:
            my_files = conn.execute(
                "SELECT id, filename, stored_name, exif_json FROM evidence WHERE case_id = ?", (case_id,)
            ).fetchall()
            seen_mentions = set()
            for r in my_files:
                ext = Path(r["filename"]).suffix
                file_path = config.EVIDENCE_DIR / r["stored_name"]
                if not file_path.exists():
                    continue
                excerpt = analysis.extract_text_excerpt(str(file_path), ext)
                if not excerpt:
                    continue
                excerpt_lower = excerpt.lower()

                for row in other_cases_and_evidence:
                    mentioned_case = bool(row["case_name"]) and row["case_name"].lower() in excerpt_lower
                    mentioned_evidence = (
                        bool(row["evidence_filename"]) and row["evidence_filename"].lower() in excerpt_lower
                    )
                    mentioned_device = row["evidence_exif_json"] and any(
                        term.lower() in excerpt_lower for term in device_terms(row["evidence_exif_json"])
                    )
                    if not (mentioned_case or mentioned_evidence or mentioned_device):
                        continue
                    dedup_key = (r["id"], row["case_id"], row["evidence_id"])
                    if dedup_key in seen_mentions:
                        continue
                    seen_mentions.add(dedup_key)

                    is_member = (
                        conn.execute(
                            "SELECT 1 FROM case_members WHERE case_id = ? AND user_id = ?",
                            (row["case_id"], user["id"]),
                        ).fetchone()
                        is not None
                    )
                    points_to_evidence = mentioned_evidence or mentioned_device
                    alerts.append(
                        _build_cross_case_alert(
                            "CONTENT_MENTION",
                            {
                                "my_id": r["id"],
                                "my_filename": r["filename"],
                                "other_id": row["evidence_id"] if points_to_evidence else None,
                                "other_filename": row["evidence_filename"] if points_to_evidence else None,
                                "other_case_id": row["case_id"],
                                "other_case_name": row["case_name"],
                            },
                            is_member,
                        )
                    )

            # 3b) Reverse direction: does an evidence item in ANOTHER case
            # literally mention THIS case's name, one of THIS case's
            # evidence filenames, or one of THIS case's evidence's EXIF
            # device? The forward pass above only catches a mention
            # written on THIS side; the exact same reference is just as
            # likely to be written in the OTHER case's report instead,
            # and detection must not depend on which of the two cases
            # you happen to be viewing.
            my_case_row = conn.execute("SELECT name FROM cases WHERE id = ?", (case_id,)).fetchone()
            my_case_name = my_case_row["name"] if my_case_row else None

            other_evidence_rows = conn.execute(
                "SELECT e.id, e.filename, e.stored_name, e.case_id, c.name AS case_name "
                "FROM evidence e JOIN cases c ON c.id = e.case_id "
                "WHERE e.case_id != ? AND c.status != 'DELETED'",
                (case_id,),
            ).fetchall()
            for o in other_evidence_rows:
                ext = Path(o["filename"]).suffix
                file_path = config.EVIDENCE_DIR / o["stored_name"]
                if not file_path.exists():
                    continue
                excerpt = analysis.extract_text_excerpt(str(file_path), ext)
                if not excerpt:
                    continue
                excerpt_lower = excerpt.lower()

                matched_my_id = None
                matched_my_filename = None
                for f in my_files:
                    if f["filename"] and f["filename"].lower() in excerpt_lower:
                        matched_my_id, matched_my_filename = f["id"], f["filename"]
                        break
                    if any(term.lower() in excerpt_lower for term in device_terms(f["exif_json"])):
                        matched_my_id, matched_my_filename = f["id"], f["filename"]
                        break
                mentioned_my_case = bool(my_case_name) and my_case_name.lower() in excerpt_lower

                if not (matched_my_id or mentioned_my_case):
                    continue

                dedup_key = (matched_my_id, o["case_id"], o["id"])
                if dedup_key in seen_mentions:
                    continue
                seen_mentions.add(dedup_key)

                is_member = (
                    conn.execute(
                        "SELECT 1 FROM case_members WHERE case_id = ? AND user_id = ?",
                        (o["case_id"], user["id"]),
                    ).fetchone()
                    is not None
                )
                alerts.append(
                    _build_cross_case_alert(
                        "CONTENT_MENTION",
                        {
                            # If no specific evidence of mine was named,
                            # fall back to this case's own name as the
                            # anchor so the alert still reads sensibly.
                            "my_id": matched_my_id,
                            "my_filename": matched_my_filename or my_case_name or "",
                            "other_id": o["id"],
                            "other_filename": o["filename"],
                            "other_case_id": o["case_id"],
                            "other_case_name": o["case_name"],
                        },
                        is_member,
                    )
                )

    return {"alerts": alerts}


def _build_cross_case_alert(alert_type: str, m, is_member: bool) -> dict:
    return {
        "type": alert_type,
        "evidence_id": m["my_id"],
        "evidence_filename": m["my_filename"],
        "visible": is_member,
        "other_case_id": m["other_case_id"] if is_member else None,
        "other_case_name": m["other_case_name"] if is_member else None,
        "other_evidence_id": m["other_id"] if is_member else None,
        "other_evidence_filename": m["other_filename"] if is_member else None,
    }


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


@router.post("/cases/{case_id}/evidence", status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    case_id: int,
    file: UploadFile = File(...),
    category: str = Form(default=config.DEFAULT_EVIDENCE_CATEGORY),
    user: dict = Depends(require_case_member),
):
    if category not in config.EVIDENCE_CATEGORIES:
        category = config.DEFAULT_EVIDENCE_CATEGORY

    original_name = file.filename or "unnamed"
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
    try:
        with open(dest_path, "wb") as out_f:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > config.MAX_UPLOAD_BYTES:
                    out_f.close()
                    os.remove(dest_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds max upload size of {config.MAX_UPLOAD_BYTES} bytes.",
                    )
                hasher.update(chunk)
                out_f.write(chunk)
    finally:
        await file.close()

    sha256_hex = hasher.hexdigest()

    if ext in IMAGE_EXTENSIONS:
        exif_status, exif_data = analysis.extract_exif(str(dest_path))
    else:
        exif_status, exif_data = "NOT_APPLICABLE", {}

    now = datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO evidence "
            "(case_id, filename, stored_name, sha256, size_bytes, content_type, "
            " uploaded_by, uploaded_at, exif_status, exif_json, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                case_id,
                original_name,
                stored_name,
                sha256_hex,
                total_bytes,
                file.content_type or "",
                user["id"],
                now,
                exif_status,
                json.dumps(exif_data, ensure_ascii=False),
                category,
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
        },
    )

    return {
        "id": evidence_id,
        "filename": original_name,
        "sha256": sha256_hex,
        "size_bytes": total_bytes,
        "exif_status": exif_status,
        "category": category,
    }


@router.get("/cases/{case_id}/evidence")
def list_evidence(case_id: int, user: dict = Depends(require_case_member)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, case_id, filename, sha256, size_bytes, content_type, "
            "uploaded_by, uploaded_at, exif_status, category FROM evidence WHERE case_id = ? "
            "ORDER BY uploaded_at DESC",
            (case_id,),
        ).fetchall()
    return [dict(r) for r in rows]


class SetCategoryRequest(BaseModel):
    category: str


@router.patch("/evidence/{evidence_id}/category")
def set_evidence_category(
    evidence_id: int, body: SetCategoryRequest, user: dict = Depends(get_current_user)
):
    if body.category not in config.EVIDENCE_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid category")

    ev = _get_evidence_or_404(evidence_id, user)
    with get_conn() as conn:
        conn.execute(
            "UPDATE evidence SET category = ? WHERE id = ?", (body.category, evidence_id)
        )
        conn.commit()

    audit.append_event(
        "EVIDENCE_CATEGORY_CHANGED",
        actor_id=user["id"],
        case_id=ev["case_id"],
        evidence_id=evidence_id,
        params={
            "username": user["username"],
            "filename": ev["filename"],
            "category": body.category,
        },
    )
    return {"id": evidence_id, "category": body.category}


def _get_evidence_or_404(evidence_id: int, user: dict) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM evidence WHERE id = ?", (evidence_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Evidence not found")
        member_row = conn.execute(
            "SELECT 1 FROM case_members WHERE case_id = ? AND user_id = ?",
            (row["case_id"], user["id"]),
        ).fetchone()
        if not member_row:
            raise HTTPException(status_code=404, detail="Evidence not found")
    return _row_evidence_dict(row)


@router.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: int, user: dict = Depends(get_current_user), lang: str = Query(default="en")):
    ev = _get_evidence_or_404(evidence_id, user)

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE evidence_id = ? ORDER BY seq ASC", (evidence_id,)
        ).fetchall()
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


@router.get("/evidence/{evidence_id}/download")
def download_evidence(evidence_id: int, user: dict = Depends(get_current_user)):
    ev = _get_evidence_or_404(evidence_id, user)
    file_path = config.EVIDENCE_DIR / ev["stored_name"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Stored file missing on disk")

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
        media_type=ev["content_type"] or "application/octet-stream",
    )


@router.post("/evidence/{evidence_id}/analyze")
def analyze_evidence(evidence_id: int, user: dict = Depends(get_current_user), lang: str = Query(default="en")):
    ev = _get_evidence_or_404(evidence_id, user)

    with get_conn() as conn:
        other_rows = conn.execute(
            "SELECT filename, stored_name, sha256, size_bytes, uploaded_at, exif_json FROM evidence "
            "WHERE case_id = ? AND id != ?",
            (ev["case_id"], evidence_id),
        ).fetchall()

    def with_content_excerpt(d: dict) -> dict:
        # Reads the item's actual text content (for .txt/.md/.csv/.json/
        # .pdf/.docx) so a report that SAYS something (e.g. "this photo
        # was taken on the victim's phone") can actually be used by the
        # model, and describes images visually -- not just filename/hash/
        # timestamp/EXIF metadata.
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
        # uploaded_at is an administrative artifact (when a file was
        # added to THIS system), not forensic evidence -- testing showed
        # the model would use it as a timing correlation signal even
        # when explicitly told not to, whenever it was present in the
        # data. Not sending it at all is the reliable fix.
        d.pop("uploaded_at", None)
        related.append(with_content_excerpt(d))

    target = with_content_excerpt(
        {
            "filename": ev["filename"],
            "stored_name": ev["stored_name"],
            "sha256": ev["sha256"],
            "exif": ev["exif"],
        }
    )

    result = analysis.analyze_evidence(target, related, lang=lang)

    if result.get("status") == "SUCCESS":
        now = datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)
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
        params={"username": user["username"], "filename": ev["filename"]},
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
    ev = _get_evidence_or_404(evidence_id, user)
    ext = Path(ev["filename"]).suffix.lower()

    if ext not in IMAGE_EXTENSIONS:
        return {"status": "NOT_APPLICABLE"}

    exif_indicators = analysis.check_exif_authenticity_indicators(ev.get("exif") or {})

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