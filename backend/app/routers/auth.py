from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from .. import audit, security
from ..database import get_conn
from ..deps import get_current_user, require_admin
from datetime import datetime, timezone
from .. import config

router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: dict


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, lang: str = Query(default="en")):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (body.username,)
        ).fetchone()

    if not row or not security.verify_password(body.password, row["password_hash"]):
        audit.append_event(
            "USER_LOGIN_FAILED",
            actor_id=row["id"] if row else None,
            params={"username": body.username},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = security.create_access_token(row["id"], row["username"], row["role"])
    audit.append_event(
        "USER_LOGIN", actor_id=row["id"], params={"username": row["username"]}
    )
    return {
        "token": token,
        "user": {"id": row["id"], "username": row["username"], "role": row["role"]},
    }


@router.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    return user


# --- Admin-only user management ---------------------------------------
# NOTE: this endpoint requires ADMIN auth (require_admin). It is not a
# public/self-registration endpoint, so it is allowed to accept `role`
# explicitly -- the caller is trusted precisely because they are already
# authenticated as ADMIN. No unauthenticated endpoint in this app accepts
# a role field.

class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)
    role: str = Field(pattern="^(ADMIN|INVESTIGATOR)$")


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: CreateUserRequest, admin: dict = Depends(require_admin)):
    now = datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (body.username,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (body.username, security.hash_password(body.password), body.role, now),
        )
        conn.commit()
        new_id = cur.lastrowid

    audit.append_event(
        "USER_CREATED",
        actor_id=admin["id"],
        params={
            "actor_username": admin["username"],
            "new_username": body.username,
            "role": body.role,
        },
    )
    return {"id": new_id, "username": body.username, "role": body.role}


@router.get("/users")
def list_users(admin: dict = Depends(require_admin)):
    with get_conn() as conn:
        rows = conn.execute("SELECT id, username, role, created_at FROM users ORDER BY username").fetchall()
    return [dict(r) for r in rows]
