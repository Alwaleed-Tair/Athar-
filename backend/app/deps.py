"""
Shared FastAPI dependencies: JWT auth, current user extraction, and case
membership enforcement (every case-scoped read/write must go through
require_case_member, which returns 404 -- not 403 -- for cases the user
is not a member of, so membership itself isn't leaked).
"""
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from . import security
from .database import get_conn


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    payload = security.decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, username, full_name, role, email, email_verified, token_version, deleted_at "
            "FROM users WHERE id = ?",
            (int(payload["sub"]),),
        ).fetchone()
    if not row or row["deleted_at"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    # A password change/reset bumps token_version, which ends every session
    # issued before it.
    if int(payload.get("tv", 0)) != int(row["token_version"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    # Unverified accounts must not reach any protected function.
    if not row["email_verified"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="EMAIL_NOT_VERIFIED")

    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"] or "",
        "role": row["role"],
        "email": row["email"] or "",
    }


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


def require_case_member(case_id: int, user: dict = Depends(get_current_user)) -> dict:
    """Every case-scoped endpoint depends on this. A case that does not
    exist, and a case the user is not a member of, both return 404 --
    identical response, so membership is never leaked."""
    with get_conn() as conn:
        case_row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if not case_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
        member_row = conn.execute(
            "SELECT 1 FROM case_members WHERE case_id = ? AND user_id = ?",
            (case_id, user["id"]),
        ).fetchone()
        if not member_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return user



def can_manage_evidence(user: dict, ev_row, case_row) -> bool:
    """
    Who may edit/delete an evidence item: the person who uploaded it, or
    the owner (creator) of the case it belongs to. Other case members can
    read it but cannot change or remove it. (Case membership itself is
    checked separately and returns 404 to outsiders.)
    """
    return user["id"] == ev_row["uploaded_by"] or user["id"] == case_row["created_by"]
