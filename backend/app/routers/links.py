"""
Access requests sent from a restricted cross-case link.

A restricted link tells an investigator that their evidence matches evidence
in a case they cannot open (see relations.restricted_matches). From that
notice they can ask for access. Only the OWNER of the other case (the account
that created it -- the same person who may share it by e-mail) sees the
request and decides. Approving adds the requester as a case member; nothing
about the case is revealed before that.

What each side learns:
- requester: only the status of their own request (pending / approved /
  declined). Never the other case's name or owner, even after a decline.
- owner: who is asking, from which of the requester's cases, which of the
  owner's files matched, why, and the requester's optional note.
Every request and decision is sealed in the custody chain.
"""
import json
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .. import audit, config
from ..database import get_conn
from ..deps import get_current_user

router = APIRouter(prefix="/api", tags=["links"])


class AccessRequestBody(BaseModel):
    note: str = Field(default="", max_length=500)


def _now() -> str:
    return datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)


def _is_member(conn, case_id: int, user_id: int) -> bool:
    return conn.execute("SELECT 1 FROM case_members WHERE case_id = ? AND user_id = ?",
                        (case_id, user_id)).fetchone() is not None


def _reason_codes(reasons_json: str) -> list[str]:
    try:
        return sorted({r["type"] for r in json.loads(reasons_json or "[]")})
    except (ValueError, TypeError, KeyError):
        return []


@router.post("/restricted-links/{link_id}/request-access", status_code=status.HTTP_201_CREATED)
def request_access(link_id: int, body: AccessRequestBody, user: dict = Depends(get_current_user)):
    if not config.RESTRICTED_LINK_ALERTS:
        raise HTTPException(status_code=404, detail="Not found")
    with get_conn() as conn:
        link = conn.execute(
            "SELECT l.*, e.case_id AS my_case_id, e.filename, e.title, e.deleted_at "
            "FROM restricted_links l JOIN evidence e ON e.id = l.evidence_id WHERE l.id = ?", (link_id,)).fetchone()
        # Same 404 for "no such link" and "not your link", so link ids can't be probed.
        if not link or link["deleted_at"] or not _is_member(conn, link["my_case_id"], user["id"]):
            raise HTTPException(status_code=404, detail="Not found")
        target = conn.execute("SELECT * FROM cases WHERE id = ? AND status != 'DELETED'",
                              (link["other_case_id"],)).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Not found")
        if _is_member(conn, target["id"], user["id"]):
            raise HTTPException(status_code=400, detail="ALREADY_MEMBER")
        if conn.execute("SELECT 1 FROM access_requests WHERE requester_id = ? AND target_case_id = ? AND status = 'PENDING'",
                        (user["id"], target["id"])).fetchone():
            raise HTTPException(status_code=400, detail="ALREADY_REQUESTED")
        cur = conn.execute(
            "INSERT INTO access_requests (link_id, requester_id, requester_case_id, target_case_id, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (link_id, user["id"], link["my_case_id"], target["id"], body.note.strip(), _now()))
        req_id = cur.lastrowid
        conn.commit()
        codes = _reason_codes(link["reasons_json"])
        my_file = link["title"] or link["filename"]
        try:
            other_ids = json.loads(link["other_evidence_ids_json"] or "[]")
        except ValueError:
            other_ids = []
        target_file = ""
        if other_ids:
            row = conn.execute("SELECT filename, title FROM evidence WHERE id = ?", (other_ids[0],)).fetchone()
            target_file = (row["title"] or row["filename"]) if row else ""

    # requester's own case: that they asked (nothing about the target case)
    audit.append_event("ACCESS_REQUESTED", actor_id=user["id"], case_id=link["my_case_id"],
                       evidence_id=link["evidence_id"],
                       params={"username": user["username"], "filename": my_file, "reason_codes": codes})
    # target case: who asked and why
    audit.append_event("ACCESS_REQUEST_RECEIVED", actor_id=user["id"], case_id=target["id"],
                       params={"requester_username": user["username"], "filename": target_file, "reason_codes": codes})
    return {"id": req_id, "status": "PENDING"}


@router.get("/access-requests")
def list_access_requests(user: dict = Depends(get_current_user)):
    """incoming: pending requests to cases this user OWNS (with the details
    the owner needs to decide). outgoing: this user's own requests, with
    their status only."""
    with get_conn() as conn:
        incoming = []
        rows = conn.execute(
            "SELECT ar.*, c.name AS target_case_name, rc.name AS requester_case_name, "
            "u.username AS requester_username, u.full_name AS requester_full_name, u.handle AS requester_handle, "
            "l.reasons_json, l.other_evidence_ids_json "
            "FROM access_requests ar JOIN cases c ON c.id = ar.target_case_id "
            "JOIN cases rc ON rc.id = ar.requester_case_id JOIN users u ON u.id = ar.requester_id "
            "JOIN restricted_links l ON l.id = ar.link_id "
            "WHERE c.created_by = ? AND ar.status = 'PENDING' AND c.status != 'DELETED' AND u.deleted_at IS NULL "
            "ORDER BY ar.id DESC", (user["id"],)).fetchall()
        for r in rows:
            try:
                ids = json.loads(r["other_evidence_ids_json"] or "[]")
            except ValueError:
                ids = []
            files = []
            for eid in ids[:5]:
                e = conn.execute("SELECT filename, title FROM evidence WHERE id = ? AND deleted_at IS NULL", (eid,)).fetchone()
                if e:
                    files.append(e["title"] or e["filename"])
            try:
                reasons = json.loads(r["reasons_json"] or "[]")
            except ValueError:
                reasons = []
            incoming.append({
                "id": r["id"], "created_at": r["created_at"], "note": r["note"],
                "requester_name": r["requester_full_name"] or r["requester_handle"] or r["requester_username"],
                "requester_username": r["requester_username"],
                "requester_case_name": r["requester_case_name"],
                "target_case_id": r["target_case_id"], "target_case_name": r["target_case_name"],
                "matched_files": files, "reasons": reasons,
            })
        outgoing = [
            {"id": r["id"], "link_id": r["link_id"], "status": r["status"], "created_at": r["created_at"],
             "decided_at": r["decided_at"], "requester_case_id": r["requester_case_id"]}
            for r in conn.execute(
                "SELECT * FROM access_requests WHERE requester_id = ? ORDER BY id DESC LIMIT 50", (user["id"],))
        ]
    return {"incoming": incoming, "outgoing": outgoing}


def _load_for_owner(conn, req_id: int, user: dict):
    r = conn.execute(
        "SELECT ar.*, c.created_by, c.name AS target_case_name, u.username AS requester_username, u.deleted_at AS requester_deleted "
        "FROM access_requests ar JOIN cases c ON c.id = ar.target_case_id JOIN users u ON u.id = ar.requester_id "
        "WHERE ar.id = ? AND c.status != 'DELETED'", (req_id,)).fetchone()
    # Only the owner may see/decide; everyone else gets the same 404.
    if not r or r["created_by"] != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    if r["status"] != "PENDING":
        raise HTTPException(status_code=400, detail="ALREADY_DECIDED")
    return r


@router.post("/access-requests/{req_id}/approve")
def approve_access_request(req_id: int, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        r = _load_for_owner(conn, req_id, user)
        if r["requester_deleted"]:
            raise HTTPException(status_code=400, detail="USER_NOT_FOUND")
        now = _now()
        try:
            conn.execute("INSERT OR IGNORE INTO case_members (case_id, user_id, added_at) VALUES (?, ?, ?)",
                         (r["target_case_id"], r["requester_id"], now))
            conn.execute("UPDATE access_requests SET status = 'APPROVED', decided_at = ?, decided_by = ? WHERE id = ?",
                         (now, user["id"], req_id))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            raise HTTPException(status_code=400, detail="ALREADY_DECIDED")
    audit.append_event("ACCESS_REQUEST_APPROVED", actor_id=user["id"], case_id=r["target_case_id"],
                       params={"actor_username": user["username"], "requester_username": r["requester_username"]})
    audit.append_event("MEMBER_ADDED", actor_id=user["id"], case_id=r["target_case_id"],
                       params={"actor_username": user["username"], "member_username": r["requester_username"]})
    return {"id": req_id, "status": "APPROVED", "case_id": r["target_case_id"]}


@router.post("/access-requests/{req_id}/decline")
def decline_access_request(req_id: int, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        r = _load_for_owner(conn, req_id, user)
        conn.execute("UPDATE access_requests SET status = 'DECLINED', decided_at = ?, decided_by = ? WHERE id = ?",
                     (_now(), user["id"], req_id))
        conn.commit()
    audit.append_event("ACCESS_REQUEST_DECLINED", actor_id=user["id"], case_id=r["target_case_id"],
                       params={"actor_username": user["username"], "requester_username": r["requester_username"]})
    return {"id": req_id, "status": "DECLINED"}
