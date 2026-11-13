"""
Relationship engine: which evidence items share something with which.

PRIVACY RULE (the one that matters): full relations -- with the other case's
name, the other file and every reason -- are built ONLY from cases the
requesting user is a member of.

The single, deliberate exception is restricted_matches(): evidence in a case
the user cannot open is compared on CONCRETE identifiers only (identical
SHA-256, or the same phone number / e-mail / IBAN). The user learns that a
match exists and which of THEIR OWN values matched; never the other case's
name, owner, file names, counts or content. Fuzzy signals (wording, device,
participant names, URLs, dates) are never used across that boundary, so the
notice cannot be turned into a search of other people's cases. The owner of
the other case sees the mirror notice in their own case, and decides on any
access request.

Every reason is deterministic and explainable: an exact hash, an exact
camera model, an exact phone/e-mail/URL/IBAN present in both texts, the same
conversation participant, or lexical TF-IDF text similarity (with the shared
words listed). Nothing is guessed.
"""
import json
from datetime import datetime, timezone

from . import config, textindex

STRENGTH = {
    "IDENTICAL_FILE": 3, "SHARED_PHONE": 3, "SHARED_EMAIL": 3, "SHARED_IBAN": 3, "SHARED_URL": 2,
    "SAME_DEVICE": 2, "SHARED_PARTICIPANT": 2, "TEXT_SIMILARITY": 2, "SHARED_DATE": 1, "SAME_CAPTURE_DAY": 1,
}


def accessible_case_ids(conn, user_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT c.id FROM cases c JOIN case_members m ON m.case_id = c.id "
        "WHERE m.user_id = ? AND c.status != 'DELETED'", (user_id,)).fetchall()
    return [r["id"] for r in rows]


def load_index(conn, case_ids: list[int]) -> dict[int, dict]:
    if not case_ids:
        return {}
    marks = ",".join("?" * len(case_ids))
    rows = conn.execute(
        f"SELECT e.*, c.name AS case_name FROM evidence e JOIN cases c ON c.id = e.case_id "
        f"WHERE e.case_id IN ({marks}) AND e.deleted_at IS NULL", case_ids).fetchall()
    index = {}
    for r in rows:
        try:
            exif = json.loads(r["exif_json"] or "{}")
        except ValueError:
            exif = {}
        make, model = exif.get("Make"), exif.get("Model")
        device = f"{make or ''} {model or ''}".strip() or None
        text = textindex.ensure_text(conn, r) if r["purged_at"] is None else ""
        ents = textindex.extract_entities(text)
        participants = set()
        for p in conn.execute(
            "SELECT DISTINCT sender FROM chat_messages WHERE evidence_id = ? AND sender IS NOT NULL", (r["id"],)):
            n = textindex.normalize(p["sender"]).strip()
            if len(n) >= 3:
                participants.add(n)
        cap = str(exif.get("DateTime") or "")[:10].replace(":", "-")
        index[r["id"]] = {
            "id": r["id"], "case_id": r["case_id"], "case_name": r["case_name"], "filename": r["filename"],
            "title": r["title"] or "", "sha256": r["sha256"], "device": device, "text": text,
            "entities": ents, "participants": participants,
            "capture_day": cap if len(cap) == 10 else None,
        }
    return index


def _pair_reasons(a: dict, b: dict) -> list[dict]:
    reasons = []
    if a["sha256"] == b["sha256"]:
        reasons.append({"type": "IDENTICAL_FILE", "value": a["sha256"][:16]})
    if a["device"] and a["device"] == b["device"]:
        reasons.append({"type": "SAME_DEVICE", "value": a["device"]})
    for kind in ("phone", "email", "iban", "url"):
        shared = a["entities"][kind] & b["entities"][kind]
        for v in sorted(shared)[:3]:
            reasons.append({"type": "SHARED_" + kind.upper(), "value": v})
    for n in sorted(a["participants"] & b["participants"])[:3]:
        reasons.append({"type": "SHARED_PARTICIPANT", "value": n})
    return reasons


def compute_relations(conn, user_id: int, case_id: int, only_other_cases: bool = False) -> list[dict]:
    """Relations between evidence of `case_id` and every other evidence the
    user can access (same case unless only_other_cases)."""
    case_ids = accessible_case_ids(conn, user_id)
    if case_id not in case_ids:
        return []
    index = load_index(conn, case_ids)
    mine = [e for e in index.values() if e["case_id"] == case_id]
    others = [e for e in index.values() if e["id"] not in {m["id"] for m in mine} or not only_other_cases]
    if only_other_cases:
        others = [e for e in index.values() if e["case_id"] != case_id]

    sims = textindex.tfidf_similarities({e["id"]: e["text"] for e in index.values()}, min_score=0.25)
    out, seen = [], set()
    for a in mine:
        for b in others:
            if a["id"] == b["id"]:
                continue
            key = tuple(sorted((a["id"], b["id"])))
            if key in seen and b["case_id"] == case_id:
                continue
            seen.add(key)
            reasons = _pair_reasons(a, b)
            sim = sims.get(key)
            if sim:
                reasons.append({"type": "TEXT_SIMILARITY", "value": f"{int(sim[0]*100)}%", "terms": sim[1]})
            # weak, context-only signals: only meaningful next to a real one
            if reasons:
                for d in sorted(a["entities"]["date"] & b["entities"]["date"])[:2]:
                    reasons.append({"type": "SHARED_DATE", "value": d})
                if a["capture_day"] and a["capture_day"] == b["capture_day"]:
                    reasons.append({"type": "SAME_CAPTURE_DAY", "value": a["capture_day"]})
            if not any(STRENGTH[r["type"]] >= 2 for r in reasons):
                continue
            score = sum(STRENGTH[r["type"]] for r in reasons)
            out.append({
                "evidence_id": a["id"], "evidence_name": a["title"] or a["filename"],
                "other_evidence_id": b["id"], "other_evidence_name": b["title"] or b["filename"],
                "other_case_id": b["case_id"], "other_case_name": b["case_name"],
                "same_case": b["case_id"] == case_id, "reasons": reasons, "score": score,
            })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out


def search_all(conn, user_id: int, query: str, case_id: int | None = None, limit: int = 60) -> dict:
    """Keyword search over case names/descriptions, evidence names/descriptions,
    full text and conversation messages -- accessible cases only."""
    q = textindex.normalize(query.strip())
    if len(q) < 2:
        return {"cases": [], "evidence": [], "messages": []}
    case_ids = accessible_case_ids(conn, user_id)
    if case_id is not None:
        case_ids = [c for c in case_ids if c == case_id]
    if not case_ids:
        return {"cases": [], "evidence": [], "messages": []}
    marks = ",".join("?" * len(case_ids))

    cases = []
    if case_id is None:
        for c in conn.execute(
            f"SELECT id, name, description, case_identifier FROM cases WHERE id IN ({marks})", case_ids):
            hay = textindex.normalize(f"{c['name']} {c['description']} {c['case_identifier']}")
            if q in hay:
                cases.append({"id": c["id"], "name": c["name"], "case_identifier": c["case_identifier"]})

    evidence, messages = [], []
    rows = conn.execute(
        f"SELECT e.*, c.name AS case_name FROM evidence e JOIN cases c ON c.id = e.case_id "
        f"WHERE e.case_id IN ({marks}) AND e.deleted_at IS NULL", case_ids).fetchall()
    for r in rows:
        where, snip = [], ""
        if q in textindex.normalize(f"{r['filename']} {r['title']}"):
            where.append("NAME")
            snip = r["title"] or r["filename"]
        if q in textindex.normalize(r["description"] or ""):
            where.append("DESCRIPTION")
            snip = snip or textindex.snippet(r["description"], q)
        try:
            exif = json.loads(r["exif_json"] or "{}")
        except ValueError:
            exif = {}
        device = f"{exif.get('Make') or ''} {exif.get('Model') or ''}".strip()
        if device and q in textindex.normalize(device):
            where.append("DEVICE")
            snip = snip or device
        text = textindex.ensure_text(conn, r) if r["purged_at"] is None else ""
        if text and q in textindex.normalize(text):
            where.append("CONTENT")
            snip = snip or textindex.snippet(text, q)
        if where:
            evidence.append({
                "evidence_id": r["id"], "case_id": r["case_id"], "case_name": r["case_name"],
                "filename": r["filename"], "title": r["title"], "matched_in": where, "snippet": snip[:260],
            })
        if len(messages) < limit:
            for m in conn.execute(
                "SELECT idx, sender, ts, body, source_ref FROM chat_messages WHERE evidence_id = ? ORDER BY idx",
                (r["id"],)):
                if q in textindex.normalize(f"{m['sender'] or ''} {m['body']}"):
                    messages.append({
                        "evidence_id": r["id"], "case_id": r["case_id"], "case_name": r["case_name"],
                        "filename": r["filename"], "idx": m["idx"], "sender": m["sender"], "ts": m["ts"],
                        "source_ref": m["source_ref"], "snippet": textindex.snippet(m["body"], q),
                    })
                    if len(messages) >= limit:
                        break
    return {"cases": cases[:limit], "evidence": evidence[:limit], "messages": messages[:limit]}


# --- restricted links: cases the user is NOT a member of ---------------------------------------

RESTRICTED_TYPES = ("IDENTICAL_FILE", "SHARED_PHONE", "SHARED_EMAIL", "SHARED_IBAN")


def _strong_reasons(a: dict, b: dict) -> list[dict]:
    """Concrete identifiers only. Every value returned is present in the
    viewer's OWN evidence `a`, so showing it reveals nothing the viewer does
    not already hold -- only the fact that it also exists elsewhere."""
    reasons = []
    if a["sha256"] == b["sha256"]:
        reasons.append({"type": "IDENTICAL_FILE", "value": a["sha256"][:16]})
    for kind in ("phone", "email", "iban"):
        for v in sorted(a["entities"][kind] & b["entities"][kind])[:3]:
            reasons.append({"type": "SHARED_" + kind.upper(), "value": v})
    return reasons


def restricted_matches(conn, user_id: int, case_id: int) -> tuple[list[dict], list[dict]]:
    """Matches between evidence of `case_id` and evidence in cases the user
    is NOT a member of. Returns (alerts, newly_detected).

    An alert carries the viewer's own evidence, the matching reason(s) and an
    opaque link id -- never the other case's id, name, owner, file names or
    content. newly_detected lists the first sightings, which the caller seals
    into the custody chain."""
    if not config.RESTRICTED_LINK_ALERTS:
        return [], []
    member_of = set(accessible_case_ids(conn, user_id))
    if case_id not in member_of:
        return [], []
    other_ids = [r["id"] for r in conn.execute("SELECT id FROM cases WHERE status != 'DELETED'")
                 if r["id"] not in member_of]
    if not other_ids:
        return [], []
    mine = load_index(conn, [case_id])
    if not mine:
        return [], []
    theirs = load_index(conn, other_ids)

    groups: dict[tuple[int, int], dict] = {}
    for a in mine.values():
        for b in theirs.values():
            reasons = _strong_reasons(a, b)
            if not reasons:
                continue
            g = groups.setdefault((a["id"], b["case_id"]), {"evidence": a, "other_ids": [], "reasons": {}})
            g["other_ids"].append(b["id"])
            for r in reasons:
                g["reasons"][(r["type"], r["value"])] = r

    now = datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)
    alerts, new = [], []
    for (ev_id, other_case), g in sorted(groups.items()):
        reasons = list(g["reasons"].values())[:6]
        ids_json = json.dumps(sorted(g["other_ids"]))
        reasons_json = json.dumps(reasons, ensure_ascii=False)
        cur = conn.execute(
            "INSERT OR IGNORE INTO restricted_links (evidence_id, other_case_id, other_evidence_ids_json, reasons_json, first_seen_at) "
            "VALUES (?, ?, ?, ?, ?)", (ev_id, other_case, ids_json, reasons_json, now))
        if cur.rowcount:
            link_id = cur.lastrowid
            new.append({"evidence_id": ev_id, "filename": g["evidence"]["title"] or g["evidence"]["filename"],
                        "reason_codes": sorted({r["type"] for r in reasons})})
        else:
            link_id = conn.execute("SELECT id FROM restricted_links WHERE evidence_id = ? AND other_case_id = ?",
                                   (ev_id, other_case)).fetchone()["id"]
            conn.execute("UPDATE restricted_links SET other_evidence_ids_json = ?, reasons_json = ? WHERE id = ?",
                         (ids_json, reasons_json, link_id))
        req = conn.execute(
            "SELECT status FROM access_requests WHERE requester_id = ? AND target_case_id = ? ORDER BY id DESC LIMIT 1",
            (user_id, other_case)).fetchone()
        types = {r["type"] for r in reasons}
        alerts.append({
            "type": "IDENTICAL_FILE" if "IDENTICAL_FILE" in types else "SHARED_CONTENT",
            "visible": False,
            "link_id": link_id,
            "evidence_id": ev_id,
            "evidence_filename": g["evidence"]["title"] or g["evidence"]["filename"],
            "reasons": reasons,
            "request_status": req["status"] if req else None,
        })
    conn.commit()
    return alerts, new
