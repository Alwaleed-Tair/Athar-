import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from .. import analysis, audit, config, i18n
from ..database import get_conn
from ..deps import get_current_user, require_admin, require_case_member

PRIORITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
CLASSIFICATIONS = {"TOP_SECRET", "CONFIDENTIAL", "RESTRICTED", "INTERNAL"}
from .evidence import build_evidence_ai_items

router = APIRouter(prefix="/api", tags=["cases"])


class CreateCaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    case_identifier: str = Field(default="", max_length=10, pattern=r"^(\d{10})?$")
    priority: str = "MEDIUM"
    classification: str = "RESTRICTED"
    status: str = "OPEN"


@router.post("/cases", status_code=status.HTTP_201_CREATED)
def create_case(body: CreateCaseRequest, user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)
    status_val = body.status if body.status in ("OPEN", "PENDING", "CLOSED") else "OPEN"
    if body.priority not in PRIORITIES:
        body.priority = "MEDIUM"
    if body.classification not in CLASSIFICATIONS:
        body.classification = "RESTRICTED"
    body.name = " ".join(body.name.split())
    if not body.name:
        raise HTTPException(status_code=400, detail="Case name is required.")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO cases (name, description, status, case_identifier, priority, classification, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (body.name, body.description, status_val, body.case_identifier, body.priority, body.classification, user["id"], now),
        )
        case_id = cur.lastrowid
        conn.execute(
            "INSERT INTO case_members (case_id, user_id, added_at) VALUES (?, ?, ?)",
            (case_id, user["id"], now),
        )
        conn.commit()

    audit.append_event(
        "CASE_CREATED",
        actor_id=user["id"],
        case_id=case_id,
        params={"username": user["username"], "case_name": body.name, "case_identifier": body.case_identifier},
    )
    return {
        "id": case_id,
        "name": body.name,
        "description": body.description,
        "status": status_val,
        "case_identifier": body.case_identifier,
        "priority": body.priority,
        "classification": body.classification,
    }


@router.get("/cases")
def list_cases(
    user: dict = Depends(get_current_user),
    search: str = Query(default=""),
    status: str = Query(default=""),
    priority: str = Query(default=""),
):
    query = (
        "SELECT c.*, "
        "(SELECT COUNT(*) FROM evidence e WHERE e.case_id = c.id AND e.deleted_at IS NULL) AS evidence_count, "
        "(SELECT u.username FROM users u WHERE u.id = c.created_by) AS creator_username, "
        "(SELECT u.full_name FROM users u WHERE u.id = c.created_by) AS creator_full_name "
        "FROM cases c "
        "JOIN case_members m ON m.case_id = c.id "
        "WHERE m.user_id = ? AND c.status != 'DELETED' "
    )
    params = [user["id"]]

    if search:
        query += " AND (c.name LIKE ? ESCAPE '\\' OR c.case_identifier LIKE ? ESCAPE '\\' OR c.description LIKE ? ESCAPE '\\') "
        like_search = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        params.extend([like_search, like_search, like_search])

    if status and status != "ALL":
        query += " AND c.status = ? "
        params.append(status)

    if priority and priority != "ALL":
        query += " AND c.priority = ? "
        params.append(priority)

    query += " ORDER BY c.created_at DESC"

    with get_conn() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(r) for r in rows]


@router.get("/cases/{case_id}")
def get_case(case_id: int, user: dict = Depends(require_case_member)):
    with get_conn() as conn:
        case_row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        evidence_count = conn.execute(
            "SELECT COUNT(*) AS c FROM evidence WHERE case_id = ? AND deleted_at IS NULL", (case_id,)
        ).fetchone()["c"]

    audit.append_event(
        "CASE_OPENED",
        actor_id=user["id"],
        case_id=case_id,
        params={"username": user["username"], "case_name": case_row["name"]},
    )
    result = dict(case_row)
    result["evidence_count"] = evidence_count
    result["is_owner"] = case_row["created_by"] == user["id"]
    return result


@router.delete("/cases/{case_id}")
def delete_case(case_id: int, user: dict = Depends(require_case_member)):
    """
    Soft-delete only: sets status to DELETED and hides the case from every
    list. Evidence, files and every audit_log row stay intact -- hard
    deleting them would tear rows out of the hash chain. Only the case
    owner, or an admin who is a member of the case, may do this.
    """
    with get_conn() as conn:
        case_row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if case_row["created_by"] != user["id"] and user["role"] != "ADMIN":
            raise HTTPException(status_code=403, detail="NOT_ALLOWED")
        conn.execute("UPDATE cases SET status = 'DELETED' WHERE id = ?", (case_id,))
        conn.commit()

    audit.append_event(
        "CASE_DELETED",
        actor_id=user["id"],
        case_id=case_id,
        params={"username": user["username"], "case_name": case_row["name"]},
    )
    return {"id": case_id, "status": "DELETED"}


class AddMemberRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)


@router.post("/cases/{case_id}/members", status_code=status.HTTP_201_CREATED)
def add_member(case_id: int, body: AddMemberRequest, user: dict = Depends(require_case_member)):
    """Grants another (verified) account access to this case. Only the case
    owner may share a case, and the person is identified by their exact
    e-mail address, so there is no user directory to browse. Being a
    platform admin gives NO way to open other people's cases."""
    now = datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)
    ident = body.email.strip()
    with get_conn() as conn:
        case_row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if case_row["created_by"] != user["id"]:
            raise HTTPException(status_code=403, detail="NOT_ALLOWED")
        member_row = conn.execute(
            "SELECT id, username FROM users WHERE (email = ? COLLATE NOCASE OR username = ? COLLATE NOCASE) "
            "AND email_verified = 1", (ident, ident)
        ).fetchone()
        if not member_row:
            raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
        already = conn.execute(
            "SELECT 1 FROM case_members WHERE case_id = ? AND user_id = ?",
            (case_id, member_row["id"]),
        ).fetchone()
        if already:
            raise HTTPException(status_code=400, detail="ALREADY_MEMBER")
        try:
            conn.execute(
                "INSERT INTO case_members (case_id, user_id, added_at) VALUES (?, ?, ?)",
                (case_id, member_row["id"], now),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            raise HTTPException(status_code=400, detail="ALREADY_MEMBER")

    audit.append_event(
        "MEMBER_ADDED",
        actor_id=user["id"],
        case_id=case_id,
        params={"actor_username": user["username"], "member_username": member_row["username"]},
    )
    return {"case_id": case_id, "user_id": member_row["id"]}


@router.delete("/cases/{case_id}/members/{member_id}")
def remove_member(case_id: int, member_id: int, user: dict = Depends(require_case_member)):
    with get_conn() as conn:
        case_row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if case_row["created_by"] != user["id"]:
            raise HTTPException(status_code=403, detail="NOT_ALLOWED")
        if member_id == case_row["created_by"]:
            raise HTTPException(status_code=400, detail="CANNOT_REMOVE_OWNER")
        m = conn.execute(
            "SELECT u.username FROM case_members cm JOIN users u ON u.id = cm.user_id "
            "WHERE cm.case_id = ? AND cm.user_id = ?", (case_id, member_id)).fetchone()
        if not m:
            raise HTTPException(status_code=404, detail="User not found")
        conn.execute("DELETE FROM case_members WHERE case_id = ? AND user_id = ?", (case_id, member_id))
        conn.commit()
    audit.append_event(
        "MEMBER_REMOVED", actor_id=user["id"], case_id=case_id,
        params={"actor_username": user["username"], "member_username": m["username"]},
    )
    return {"case_id": case_id, "user_id": member_id}


@router.get("/cases/{case_id}/members")
def list_members(case_id: int, user: dict = Depends(require_case_member)):
    with get_conn() as conn:
        owner = conn.execute("SELECT created_by FROM cases WHERE id = ?", (case_id,)).fetchone()["created_by"]
        rows = conn.execute(
            "SELECT u.id, u.username, u.full_name, u.role, m.added_at FROM users u "
            "JOIN case_members m ON m.user_id = u.id WHERE m.case_id = ? ORDER BY m.added_at",
            (case_id,),
        ).fetchall()
    return [{**dict(r), "is_owner": r["id"] == owner} for r in rows]


@router.get("/cases/{case_id}/audit")
def case_audit(
    case_id: int,
    user: dict = Depends(require_case_member),
    lang: str = Query(default="en"),
):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE case_id = ? ORDER BY seq ASC", (case_id,)
        ).fetchall()

    out = []
    for r in rows:
        import json as _json

        try:
            params = _json.loads(r["params_json"])
        except Exception:
            params = {}
        out.append(
            {
                "seq": r["seq"],
                "action": r["action"],
                "ts": r["ts"],
                "previous_hash": r["previous_hash"],
                "event_hash": r["event_hash"],
                "evidence_id": r["evidence_id"],
                "message": i18n.build_message(r["action"], params, lang),
            }
        )
    return out


@router.get("/cases/{case_id}/verify")
def verify_case_chain(
    case_id: int,
    user: dict = Depends(require_case_member),
    lang: str = Query(default="en"),
):
    result = audit.verify_chain(case_id=case_id)
    audit.append_event(
        "CHAIN_VERIFIED",
        actor_id=user["id"],
        case_id=case_id,
        params={"username": user["username"], "intact": result["intact"]},
    )
    result["message"] = i18n.build_message(
        "CHAIN_VERIFIED", {"username": user["username"], "intact": result["intact"]}, lang
    )
    return result


@router.get("/audit/verify-all")
def verify_global_chain(admin: dict = Depends(require_admin)):
    """Whole-database chain verification (ADMIN only, not case-scoped)."""
    return audit.verify_chain(case_id=None)


@router.get("/cases/{case_id}/summary")
def get_case_summary(case_id: int, user: dict = Depends(require_case_member)):
    """
    Returns the last generated (cached) formal case summary, or
    {"status": "NOT_GENERATED"} if none exists yet. Never generates one
    itself -- generation only happens via the POST endpoint below, so
    the frontend controls exactly when the (costly) AI call happens:
    automatically once on first view, and manually afterward.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT summary_text, lang, generated_at FROM case_summary WHERE case_id = ?",
            (case_id,),
        ).fetchone()
    if not row:
        return {"status": "NOT_GENERATED"}
    return {
        "status": "SUCCESS",
        "summary_text": row["summary_text"],
        "lang": row["lang"],
        "generated_at": row["generated_at"],
    }


@router.post("/cases/{case_id}/summary/generate")
def generate_case_summary_endpoint(
    case_id: int, user: dict = Depends(require_case_member), lang: str = Query(default="en")
):
    """
    Generates (or re-generates) the formal case summary and caches it,
    overwriting any previous one. Every call to this endpoint is a real
    AI request -- the frontend must not call this on every page view,
    only when there is no cached summary yet or the investigator
    explicitly asks to refresh it.
    """
    with get_conn() as conn:
        case_row = conn.execute("SELECT name FROM cases WHERE id = ?", (case_id,)).fetchone()
        if not case_row:
            raise HTTPException(status_code=404, detail="Case not found")
        items = build_evidence_ai_items(conn, case_id)

    if not items:
        return {"status": "NO_EVIDENCE"}

    result = analysis.generate_case_summary(case_row["name"], items, lang=lang)

    if result.get("status") == "SUCCESS":
        now = datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO case_summary (case_id, summary_text, lang, generated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(case_id) DO UPDATE SET "
                "summary_text = excluded.summary_text, lang = excluded.lang, generated_at = excluded.generated_at",
                (case_id, result["summary_text"], lang, now),
            )
            conn.commit()
        audit.append_event(
            "CASE_SUMMARY_GENERATED",
            actor_id=user["id"],
            case_id=case_id,
            params={"username": user["username"], "case_name": case_row["name"]},
        )

    return result
