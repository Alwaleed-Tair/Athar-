import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from .. import audit, config, mailer, ratelimit, security
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


def _now() -> str:
    return datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def _user_public(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"] or "",
        "role": row["role"],
        "email": row["email"] or "",
        "email_verified": bool(row["email_verified"]),
    }


# --- E-mail verification --------------------------------------------------

def _issue_verification_email(request: Request, user_row) -> str:
    """Creates a fresh single-use token (older unused ones are revoked) and
    mails the link. Returns the mailer result (SENT/CONSOLE/NOT_CONFIGURED/FAILED)."""
    raw = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=config.EMAIL_TOKEN_TTL_HOURS)
    with get_conn() as conn:
        conn.execute(
            "UPDATE email_tokens SET used_at = ? WHERE user_id = ? AND purpose = 'VERIFY' AND used_at IS NULL",
            (now.strftime(config.TIMESTAMP_FORMAT), user_row["id"]),
        )
        conn.execute(
            "INSERT INTO email_tokens (user_id, token_hash, purpose, created_at, expires_at) VALUES (?, ?, 'VERIFY', ?, ?)",
            (user_row["id"], security.hash_token(raw),
             now.strftime(config.TIMESTAMP_FORMAT), expires.strftime(config.TIMESTAMP_FORMAT)),
        )
        conn.commit()

    base = config.PUBLIC_URL or str(request.base_url).rstrip("/")
    link = f"{base}/?verify={raw}"
    hours = config.EMAIL_TOKEN_TTL_HOURS
    name = user_row["full_name"] or user_row["email"]
    text = (
        f"مرحباً {name}،\n"
        f"لتفعيل حسابك في منصة أثر (ATHAR) افتح الرابط التالي (صالح لمدة {hours} ساعة):\n{link}\n\n"
        "إذا لم تطلب إنشاء هذا الحساب فتجاهل هذه الرسالة.\n\n"
        "------------------------------\n"
        f"Hello {name},\n"
        f"To activate your ATHAR account open this link (valid for {hours} hours):\n{link}\n\n"
        "If you did not create this account, ignore this message.\n"
    )
    return mailer.send_mail(user_row["email"], "تفعيل حساب أثر / Activate your ATHAR account", text)


# --- Login ---------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=500)


@router.post("/auth/login")
def login(body: LoginRequest, request: Request, lang: str = Query(default="en")):
    target_username = body.username.strip()
    ip = _client_ip(request)
    keys = [f"u:{target_username.lower()}", f"ip:{ip}"]

    for k in keys:
        wait = ratelimit.login_locked(k, config.LOGIN_MAX_FAILURES * (4 if k.startswith("ip:") else 1),
                                      config.LOGIN_LOCK_SECONDS)
        if wait:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="TOO_MANY_ATTEMPTS",
                headers={"Retry-After": str(wait)},
            )

    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE OR (email != '' AND email = ? COLLATE NOCASE)",
            (target_username, target_username),
        ).fetchone()
        # "admin@athar.gov" style sign-in for accounts whose username has
        # no domain (e.g. the bootstrap "admin").
        if not row and "@" in target_username:
            alias = target_username.split("@")[0]
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (alias,)
            ).fetchone()

    # Unknown username must fail exactly like a wrong password (401).
    valid = bool(row) and security.verify_password(body.password, row["password_hash"])

    if not valid:
        for k in keys:
            ratelimit.record_login_failure(k)
        audit.append_event(
            "USER_LOGIN_FAILED",
            actor_id=row["id"] if row else None,
            params={"username": target_username[:120]},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    ratelimit.clear_login_failures(keys[0])

    # Correct password but e-mail not yet verified: no session is issued.
    if not row["email_verified"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="EMAIL_NOT_VERIFIED")

    token = security.create_access_token(row["id"], row["username"], row["role"], row["token_version"])
    audit.append_event("USER_LOGIN", actor_id=row["id"], params={"username": row["username"]})
    return {"token": token, "user": _user_public(row)}


# --- Self-registration ---------------------------------------------------
# Creates an INVESTIGATOR account that stays INACTIVE until the e-mail
# address is verified. It can never create an ADMIN (role is fixed
# server-side).

class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(max_length=500)


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request):
    if not ratelimit.allow(f"register:{_client_ip(request)}", 10, 3600):
        raise HTTPException(status_code=429, detail="TOO_MANY_ATTEMPTS")

    full_name = " ".join(body.full_name.split())
    email = body.username.strip().lower()

    if len(full_name) < 2:
        raise HTTPException(status_code=400, detail="Full name is required.")
    if not EMAIL_RE.match(email) or not email.endswith(ALLOWED_EMAIL_DOMAINS):
        raise HTTPException(
            status_code=400,
            detail="Email must end with " + " / ".join(ALLOWED_EMAIL_DOMAINS) + ".",
        )
    _require_strong_password(body.password)

    now = _now()
    with get_conn() as conn:
        if conn.execute(
            "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE", (email, email)
        ).fetchone():
            raise HTTPException(status_code=400, detail="An account with this email already exists.")
        cur = conn.execute(
            "INSERT INTO users (username, email, full_name, password_hash, role, created_at, email_verified) "
            "VALUES (?, ?, ?, ?, 'INVESTIGATOR', ?, 0)",
            (email, email, full_name, security.hash_password(body.password), now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()

    audit.append_event(
        "USER_REGISTERED",
        actor_id=row["id"],
        params={"username": email, "full_name": full_name},
    )
    delivery = _issue_verification_email(request, row)
    return {"status": "VERIFICATION_REQUIRED", "email": email, "email_delivery": delivery}


class VerifyRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


@router.post("/auth/verify-email")
def verify_email(body: VerifyRequest, request: Request):
    if not ratelimit.allow(f"verify:{_client_ip(request)}", 30, 3600):
        raise HTTPException(status_code=429, detail="TOO_MANY_ATTEMPTS")
    token_hash = security.hash_token(body.token.strip())
    now = _now()
    with get_conn() as conn:
        t = conn.execute(
            "SELECT * FROM email_tokens WHERE token_hash = ? AND purpose = 'VERIFY'", (token_hash,)
        ).fetchone()
        if not t:
            raise HTTPException(status_code=400, detail="TOKEN_INVALID")
        user = conn.execute("SELECT * FROM users WHERE id = ?", (t["user_id"],)).fetchone()
        if user and user["email_verified"]:
            return {"status": "ALREADY_VERIFIED"}
        if t["used_at"]:
            raise HTTPException(status_code=400, detail="TOKEN_INVALID")
        if t["expires_at"] < now:
            raise HTTPException(status_code=400, detail="TOKEN_EXPIRED")
        conn.execute("UPDATE email_tokens SET used_at = ? WHERE id = ?", (now, t["id"]))
        conn.execute("UPDATE users SET email_verified = 1, updated_at = ? WHERE id = ?", (now, t["user_id"]))
        conn.commit()

    audit.append_event("EMAIL_VERIFIED", actor_id=t["user_id"], params={"username": user["username"]})
    return {"status": "VERIFIED"}


class ResendRequest(BaseModel):
    email: str = Field(max_length=200)


@router.post("/auth/resend-verification")
def resend_verification(body: ResendRequest, request: Request):
    """Always answers the same way whether or not the address has an
    account, so it can't be used to discover registered e-mails."""
    email = body.email.strip().lower()
    if not ratelimit.allow(f"resend-ip:{_client_ip(request)}", 10, 3600):
        raise HTTPException(status_code=429, detail="TOO_MANY_ATTEMPTS")
    if not ratelimit.allow(f"resend:{email}", 1, config.EMAIL_RESEND_COOLDOWN_SECONDS):
        raise HTTPException(
            status_code=429, detail="RESEND_TOO_SOON",
            headers={"Retry-After": str(config.EMAIL_RESEND_COOLDOWN_SECONDS)},
        )
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE AND email_verified = 0", (email,)
        ).fetchone()
    delivery = "SENT" if mailer.delivery_available() else "NOT_CONFIGURED"
    if row:
        delivery = _issue_verification_email(request, row)
    return {"status": "ACCEPTED", "email_delivery": delivery}


# --- Current user / account management ------------------------------------

@router.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return {**_user_public(row), "created_at": row["created_at"]}


class UpdateProfileRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)


@router.patch("/auth/me")
def update_profile(body: UpdateProfileRequest, user: dict = Depends(get_current_user)):
    """Edits ONLY the signed-in user's own display name. The id always comes
    from the token, never from the request, so nobody can edit another user."""
    full_name = " ".join(body.full_name.split())
    if len(full_name) < 2:
        raise HTTPException(status_code=400, detail="Full name is required.")
    with get_conn() as conn:
        conn.execute("UPDATE users SET full_name = ?, updated_at = ? WHERE id = ?", (full_name, _now(), user["id"]))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    audit.append_event(
        "PROFILE_UPDATED", actor_id=user["id"],
        params={"username": user["username"], "full_name": full_name},
    )
    return _user_public(row)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=500)
    new_password: str = Field(max_length=500)


@router.post("/auth/change-password")
def change_password(body: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    if not security.verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="CURRENT_PASSWORD_WRONG")
    _require_strong_password(body.new_password)
    if body.new_password == body.current_password:
        raise HTTPException(status_code=400, detail="PASSWORD_UNCHANGED")

    new_version = row["token_version"] + 1
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, token_version = ?, updated_at = ? WHERE id = ?",
            (security.hash_password(body.new_password), new_version, _now(), user["id"]),
        )
        conn.commit()
    audit.append_event("PASSWORD_CHANGED", actor_id=user["id"], params={"username": user["username"]})
    # Every other session is now invalid; hand back a fresh token so this one continues.
    return {"status": "PASSWORD_CHANGED",
            "token": security.create_access_token(user["id"], row["username"], row["role"], new_version)}


# --- Admin-only user management -----------------------------------------

class CreateUserRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(max_length=500)
    role: str = Field(pattern="^(ADMIN|INVESTIGATOR)$")


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: CreateUserRequest, admin: dict = Depends(require_admin)):
    full_name = " ".join(body.full_name.split())
    username = body.username.strip()
    if re.search(r"\s", username):
        raise HTTPException(status_code=400, detail="Username must not contain spaces.")
    _require_strong_password(body.password)

    email = username.lower() if EMAIL_RE.match(username) else ""
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone():
            raise HTTPException(status_code=400, detail="Username already exists.")
        cur = conn.execute(
            "INSERT INTO users (username, email, full_name, password_hash, role, created_at, email_verified) "
            "VALUES (?, ?, ?, ?, ?, ?, 1)",
            (username, email, full_name, security.hash_password(body.password), body.role, _now()),
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
            "SELECT id, username, full_name, role, email, email_verified, created_at FROM users ORDER BY created_at"
        ).fetchall()
    return [{**dict(r), "email_verified": bool(r["email_verified"])} for r in rows]


@router.post("/users/{user_id}/verify")
def admin_verify_user(user_id: int, admin: dict = Depends(require_admin)):
    """Manual activation. This exists for deployments with no outgoing
    mail server configured; it is logged in the audit trail."""
    with get_conn() as conn:
        row = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        conn.execute("UPDATE users SET email_verified = 1, updated_at = ? WHERE id = ?", (_now(), user_id))
        conn.commit()
    audit.append_event(
        "EMAIL_VERIFIED_BY_ADMIN", actor_id=admin["id"],
        params={"actor_username": admin["username"], "target_username": row["username"]},
    )
    return {"id": user_id, "email_verified": True}


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(max_length=500)


@router.post("/users/{user_id}/password")
def reset_user_password(user_id: int, body: ResetPasswordRequest, admin: dict = Depends(require_admin)):
    """Admin sets a new password for a user (all of that user's existing
    sessions are ended)."""
    _require_strong_password(body.new_password)
    with get_conn() as conn:
        row = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        conn.execute(
            "UPDATE users SET password_hash = ?, token_version = token_version + 1, updated_at = ? WHERE id = ?",
            (security.hash_password(body.new_password), _now(), user_id),
        )
        conn.commit()

    audit.append_event(
        "PASSWORD_RESET",
        actor_id=admin["id"],
        params={"actor_username": admin["username"], "target_username": row["username"]},
    )
    return {"id": user_id, "status": "PASSWORD_RESET"}
