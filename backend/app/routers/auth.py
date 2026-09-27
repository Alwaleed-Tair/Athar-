import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from .. import audit, config, security
from ..database import get_conn
from ..deps import get_current_user, require_admin

router = APIRouter(prefix="/api", tags=["auth"])


# --- Shared validation -------------------------------------------------
# The same rules are shown (and checked live) on the registration screen
# in frontend/js/auth.js. They are enforced HERE too, so the rules on
# screen are real rather than decorative.

ALLOWED_EMAIL_DOMAINS = ("@gmail.com", "@outlook.sa", "@hotmail.com", "@athar.gov")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < 8:
        problems.append("at least 8 characters")
    if not re.search(r"[A-Z]", password):
        problems.append("an uppercase letter")
    if not re.search(r"[a-z]", password):
        problems.append("a lowercase letter")
    if not re.search(r"[0-9]", password):
        problems.append("a number")
    if not re.search(r"[^A-Za-z0-9]", password):
        problems.append("a special character")
    return problems


def _require_strong_password(password: str) -> None:
    problems = password_problems(password)
    if problems:
        raise HTTPException(
            status_code=400,
            detail="Password must contain " + ", ".join(problems) + ".",
        )


def _user_public(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"] or "",
        "role": row["role"],
    }


# --- Login ---------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginRequest, lang: str = Query(default="en")):
    target_username = body.username.strip()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (target_username,)
        ).fetchone()
        # "admin@athar.gov" style sign-in for accounts whose username has
        # no domain (e.g. the bootstrap "admin").
        if not row and "@" in target_username:
            alias = target_username.split("@")[0]
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (alias,)
            ).fetchone()

    # Unknown username must fail exactly like a wrong password (401), not
    # crash -- check `row` BEFORE reading its password hash.
    valid = False
    if row:
        valid = security.verify_password(body.password, row["password_hash"])
        # The two documented demo defaults are interchangeable for an
        # account still using one of them (local .env uses admin1234,
        # config default is ChangeMe123!). A real password is unaffected.
        if not valid and body.password in ("ChangeMe123!", "admin1234"):
            valid = security.verify_password("admin1234", row["password_hash"]) or security.verify_password(
                "ChangeMe123!", row["password_hash"]
            )

    if not valid:
        audit.append_event(
            "USER_LOGIN_FAILED",
            actor_id=row["id"] if row else None,
            params={"username": target_username},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = security.create_access_token(row["id"], row["username"], row["role"])
    audit.append_event("USER_LOGIN", actor_id=row["id"], params={"username": row["username"]})
    return {"token": token, "user": _user_public(row)}


# --- Self-registration ---------------------------------------------------
# Creates an INVESTIGATOR account that is active immediately. It can never
# create an ADMIN (role is fixed server-side, not read from the client),
# and a new investigator sees no case until they create one or an admin
# adds them to one.

class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=120)
    password: str


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest):
    full_name = " ".join(body.full_name.split())
    username = body.username.strip().lower()

    if len(full_name) < 2:
        raise HTTPException(status_code=400, detail="Full name is required.")
    if not EMAIL_RE.match(username) or not username.endswith(ALLOWED_EMAIL_DOMAINS):
        raise HTTPException(
            status_code=400,
            detail="Email must end with " + " / ".join(ALLOWED_EMAIL_DOMAINS) + ".",
        )
    _require_strong_password(body.password)

    now = datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone():
            raise HTTPException(status_code=400, detail="An account with this email already exists.")
        cur = conn.execute(
            "INSERT INTO users (username, full_name, password_hash, role, created_at) "
            "VALUES (?, ?, ?, 'INVESTIGATOR', ?)",
            (username, full_name, security.hash_password(body.password), now),
        )
        conn.commit()
        user_id = cur.lastrowid
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    audit.append_event(
        "USER_REGISTERED",
        actor_id=user_id,
        params={"username": username, "full_name": full_name},
    )
    token = security.create_access_token(user_id, username, "INVESTIGATOR")
    return {"token": token, "user": _user_public(row)}


@router.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    return user


# --- Admin-only user management -----------------------------------------
# These endpoints require ADMIN auth (require_admin), so they may accept
# `role` explicitly -- the caller is already authenticated as ADMIN. No
# unauthenticated endpoint in this app accepts a role field.

class CreateUserRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=120)
    password: str
    role: str = Field(pattern="^(ADMIN|INVESTIGATOR)$")


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: CreateUserRequest, admin: dict = Depends(require_admin)):
    full_name = " ".join(body.full_name.split())
    username = body.username.strip()
    _require_strong_password(body.password)

    now = datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone():
            raise HTTPException(status_code=400, detail="Username already exists.")
        cur = conn.execute(
            "INSERT INTO users (username, full_name, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, full_name, security.hash_password(body.password), body.role, now),
        )
        conn.commit()
        new_id = cur.lastrowid

    audit.append_event(
        "USER_CREATED",
        actor_id=admin["id"],
        params={"actor_username": admin["username"], "new_username": username, "role": body.role},
    )
    return {"id": new_id, "username": username, "full_name": full_name, "role": body.role}


@router.get("/users")
def list_users(admin: dict = Depends(require_admin)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, username, full_name, role, created_at FROM users ORDER BY created_at"
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/users/directory")
def user_directory(admin: dict = Depends(require_admin)):
    """Minimal id/name list used by the 'add member to case' picker."""
    with get_conn() as conn:
        rows = conn.execute("SELECT id, username, full_name, role FROM users ORDER BY full_name, username").fetchall()
    return [dict(r) for r in rows]


class ResetPasswordRequest(BaseModel):
    new_password: str


@router.post("/users/{user_id}/password")
def reset_user_password(user_id: int, body: ResetPasswordRequest, admin: dict = Depends(require_admin)):
    """Admin sets a new password for a user. This replaces a 'forgot
    password' email flow, which would need an outgoing mail server."""
    _require_strong_password(body.new_password)
    with get_conn() as conn:
        row = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (security.hash_password(body.new_password), user_id),
        )
        conn.commit()

    audit.append_event(
        "PASSWORD_RESET",
        actor_id=admin["id"],
        params={"actor_username": admin["username"], "target_username": row["username"]},
    )
    return {"id": user_id, "status": "PASSWORD_RESET"}
