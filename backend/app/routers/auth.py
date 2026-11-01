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


HANDLE_RE = re.compile(r"^[\w.\-]{3,30}$")


def _unique_handle(conn, base: str) -> str:
    base = re.sub(r"[^\w.\-]", "", (base or "").split("@")[0])[:26] or "user"
    if len(base) < 3:
        base = (base + "user")[:26]
    cand, n = base, 1
    while conn.execute("SELECT 1 FROM users WHERE handle = ? COLLATE NOCASE", (cand,)).fetchone():
        n += 1
        cand = f"{base}{n}"
    return cand


def _user_public(row) -> dict:
    return {
        "id": row["id"],
        "handle": row["handle"] or "",
        "username": row["username"],
        "full_name": row["full_name"] or "",
        "role": row["role"],
        "email": row["email"] or "",
        "email_verified": bool(row["email_verified"]),
    }


# --- E-mail verification --------------------------------------------------

def _issue_email(request: Request, user_row, purpose: str) -> str:
    """Creates a fresh single-use token (older unused ones of the same
    purpose are revoked) and mails the link. purpose: VERIFY | RESET.
    Returns SENT/CONSOLE/NOT_CONFIGURED/FAILED."""
    raw = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    ttl = timedelta(hours=config.EMAIL_TOKEN_TTL_HOURS) if purpose == "VERIFY" else timedelta(hours=1)
    with get_conn() as conn:
        conn.execute(
            "UPDATE email_tokens SET used_at = ? WHERE user_id = ? AND purpose = ? AND used_at IS NULL",
            (now.strftime(config.TIMESTAMP_FORMAT), user_row["id"], purpose),
        )
        conn.execute(
            "INSERT INTO email_tokens (user_id, token_hash, purpose, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (user_row["id"], security.hash_token(raw), purpose,
             now.strftime(config.TIMESTAMP_FORMAT), (now + ttl).strftime(config.TIMESTAMP_FORMAT)),
        )
        conn.commit()

    base = config.PUBLIC_URL or str(request.base_url).rstrip("/")
    name = user_row["full_name"] or user_row["email"]
    if purpose == "VERIFY":
        link = f"{base}/?verify={raw}"
        hours = config.EMAIL_TOKEN_TTL_HOURS
        text = (
            f"مرحباً {name}،\nلتفعيل حسابك في منصة أثر (ATHAR) افتح الرابط التالي (صالح لمدة {hours} ساعة):\n{link}\n\n"
            "إذا لم تطلب إنشاء هذا الحساب فتجاهل هذه الرسالة.\n\n------------------------------\n"
            f"Hello {name},\nTo activate your ATHAR account open this link (valid for {hours} hours):\n{link}\n\n"
            "If you did not create this account, ignore this message.\n"
        )
        subject = "تفعيل حساب أثر / Activate your ATHAR account"
    else:
        link = f"{base}/?reset={raw}"
        text = (
            f"مرحباً {name}،\nطُلب تعيين كلمة مرور جديدة لحسابك في أثر. افتح الرابط التالي (صالح لمدة ساعة واحدة ويعمل مرة واحدة):\n{link}\n\n"
            "إذا لم تطلب ذلك فتجاهل هذه الرسالة؛ كلمة مرورك لم تتغير.\n\n------------------------------\n"
            f"Hello {name},\nA new password was requested for your ATHAR account. Open this link (valid 1 hour, single use):\n{link}\n\n"
            "If you did not request this, ignore this message; your password has not changed.\n"
        )
        subject = "إعادة تعيين كلمة المرور / Reset your ATHAR password"
    return mailer.send_mail(user_row["email"], subject, text)


def _issue_verification_email(request: Request, user_row) -> str:
    return _issue_email(request, user_row, "VERIFY")


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
            "SELECT * FROM users WHERE deleted_at IS NULL AND (username = ? COLLATE NOCASE "
            "OR (email != '' AND email = ? COLLATE NOCASE) OR handle = ? COLLATE NOCASE)",
            (target_username, target_username, target_username),
        ).fetchone()
        # "admin@athar.gov" style sign-in for accounts whose username has
        # no domain (e.g. the bootstrap "admin").
        if not row and "@" in target_username:
            alias = target_username.split("@")[0]
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE AND deleted_at IS NULL", (alias,)
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
            "INSERT INTO users (username, email, full_name, password_hash, role, created_at, email_verified, handle) "
            "VALUES (?, ?, ?, ?, 'INVESTIGATOR', ?, 0, ?)",
            (email, email, full_name, security.hash_password(body.password), now, _unique_handle(conn, email)),
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
    handle: str | None = Field(default=None, max_length=60)


@router.patch("/auth/me")
def update_profile(body: UpdateProfileRequest, user: dict = Depends(get_current_user)):
    """Edits ONLY the signed-in user's own display name and username. The id
    always comes from the token, never from the request."""
    full_name = " ".join(body.full_name.split())
    if len(full_name) < 2:
        raise HTTPException(status_code=400, detail="Full name is required.")
    with get_conn() as conn:
        cur_row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        handle = cur_row["handle"]
        if body.handle is not None and body.handle.strip() != (handle or ""):
            handle = body.handle.strip()
            if not HANDLE_RE.match(handle):
                raise HTTPException(status_code=400, detail="INVALID_HANDLE")
            if conn.execute(
                "SELECT 1 FROM users WHERE handle = ? COLLATE NOCASE AND id != ?", (handle, user["id"])
            ).fetchone():
                raise HTTPException(status_code=400, detail="HANDLE_TAKEN")
        conn.execute("UPDATE users SET full_name = ?, handle = ?, updated_at = ? WHERE id = ?",
                     (full_name, handle, _now(), user["id"]))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    audit.append_event(
        "PROFILE_UPDATED", actor_id=user["id"],
        params={"username": user["username"], "full_name": full_name, "handle": handle or ""},
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


# --- Password reset by e-mail ---------------------------------------------------

class ForgotRequest(BaseModel):
    email: str = Field(max_length=200)


@router.post("/auth/forgot-password")
def forgot_password(body: ForgotRequest, request: Request):
    """Always answers the same way whether or not the address has an account."""
    email = body.email.strip().lower()
    if not ratelimit.allow(f"forgot-ip:{_client_ip(request)}", 10, 3600):
        raise HTTPException(status_code=429, detail="TOO_MANY_ATTEMPTS")
    if not ratelimit.allow(f"forgot:{email}", 1, config.EMAIL_RESEND_COOLDOWN_SECONDS):
        raise HTTPException(status_code=429, detail="RESEND_TOO_SOON",
                            headers={"Retry-After": str(config.EMAIL_RESEND_COOLDOWN_SECONDS)})
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email != '' AND email = ? COLLATE NOCASE AND deleted_at IS NULL", (email,)
        ).fetchone()
    delivery = "SENT" if mailer.delivery_available() else "NOT_CONFIGURED"
    if row:
        delivery = _issue_email(request, row, "RESET")
    return {"status": "ACCEPTED", "email_delivery": delivery}


class ResetRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(max_length=500)


@router.post("/auth/reset-password")
def reset_password(body: ResetRequest, request: Request):
    if not ratelimit.allow(f"reset:{_client_ip(request)}", 20, 3600):
        raise HTTPException(status_code=429, detail="TOO_MANY_ATTEMPTS")
    now = _now()
    with get_conn() as conn:
        t = conn.execute(
            "SELECT * FROM email_tokens WHERE token_hash = ? AND purpose = 'RESET'",
            (security.hash_token(body.token.strip()),),
        ).fetchone()
        if not t or t["used_at"]:
            raise HTTPException(status_code=400, detail="TOKEN_INVALID")
        if t["expires_at"] < now:
            raise HTTPException(status_code=400, detail="TOKEN_EXPIRED")
        user = conn.execute("SELECT * FROM users WHERE id = ? AND deleted_at IS NULL", (t["user_id"],)).fetchone()
        if not user:
            raise HTTPException(status_code=400, detail="TOKEN_INVALID")
    _require_strong_password(body.new_password)
    with get_conn() as conn:
        conn.execute("UPDATE email_tokens SET used_at = ? WHERE id = ?", (now, t["id"]))
        # Receiving the link proves control of the mailbox, so the e-mail is verified too.
        conn.execute(
            "UPDATE users SET password_hash = ?, token_version = token_version + 1, email_verified = 1, updated_at = ? WHERE id = ?",
            (security.hash_password(body.new_password), now, user["id"]),
        )
        conn.commit()
    ratelimit.clear_login_failures(f"u:{user['username'].lower()}")
    audit.append_event("PASSWORD_RESET_BY_EMAIL", actor_id=user["id"], params={"username": user["username"]})
    return {"status": "PASSWORD_RESET"}


# --- Self-service account deletion ---------------------------------------------------

class DeleteAccountRequest(BaseModel):
    password: str = Field(max_length=500)


@router.post("/auth/delete-account")
def delete_account(body: DeleteAccountRequest, user: dict = Depends(get_current_user)):
    """
    Deletes the signed-in user's account (password required).
    * Cases you own that other people belong to are handed to the member who
      joined first; cases only you belong to are archived (their evidence goes
      through the normal 30-day retention).
    * Your personal data is erased: name, e-mail, username, password hash,
      contact messages and tokens; the row stays only as "Deleted user" so
      existing evidence and the audit chain keep their references.
    * Audit-log entries are append-only and still contain the name/e-mail
      that were recorded at the time (see the privacy policy).
    The last administrator cannot delete their account.
    """
    from .. import integrity

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    if not security.verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="CURRENT_PASSWORD_WRONG")
    with get_conn() as conn:
        if row["role"] == "ADMIN":
            admins = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role = 'ADMIN' AND deleted_at IS NULL").fetchone()["c"]
            if admins <= 1:
                raise HTTPException(status_code=400, detail="LAST_ADMIN")

    transferred, archived = [], []
    now = _now()
    with get_conn() as conn:
        for c in conn.execute("SELECT id FROM cases WHERE created_by = ? AND status != 'DELETED'", (user["id"],)).fetchall():
            nxt = conn.execute(
                "SELECT user_id FROM case_members WHERE case_id = ? AND user_id != ? ORDER BY added_at LIMIT 1",
                (c["id"], user["id"])).fetchone()
            if nxt:
                conn.execute("UPDATE cases SET created_by = ? WHERE id = ?", (nxt["user_id"], c["id"]))
                transferred.append(c["id"])
            else:
                conn.execute("UPDATE cases SET status = 'DELETED' WHERE id = ?", (c["id"],))
                for ev in conn.execute("SELECT id FROM evidence WHERE case_id = ? AND deleted_at IS NULL", (c["id"],)).fetchall():
                    conn.execute("UPDATE evidence SET deleted_at = ?, deleted_by = ? WHERE id = ?", (now, user["id"], ev["id"]))
                    integrity.delete_derived_data(conn, ev["id"], c["id"])
                archived.append(c["id"])
        conn.commit()
    for cid in transferred + archived:
        audit.append_event("ACCOUNT_DELETED", actor_id=user["id"], case_id=cid,
                           params={"username": user["username"], "case_action": "TRANSFERRED" if cid in transferred else "ARCHIVED"})
    audit.append_event("ACCOUNT_DELETED", actor_id=user["id"], params={"username": user["username"], "case_action": "NONE"})

    with get_conn() as conn:
        conn.execute("DELETE FROM case_members WHERE user_id = ?", (user["id"],))
        conn.execute("DELETE FROM contact_messages WHERE user_id = ?", (user["id"],))
        conn.execute("DELETE FROM email_tokens WHERE user_id = ?", (user["id"],))
        conn.execute(
            "UPDATE users SET username = ?, email = '', full_name = '', handle = NULL, password_hash = '!', "
            "token_version = token_version + 1, email_verified = 0, deleted_at = ?, updated_at = ? WHERE id = ?",
            (f"deleted-{user['id']}", now, now, user["id"]),
        )
        conn.commit()
    return {"status": "DELETED", "cases_transferred": len(transferred), "cases_archived": len(archived)}


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
            "INSERT INTO users (username, email, full_name, password_hash, role, created_at, email_verified, handle) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            (username, email, full_name, security.hash_password(body.password), body.role, _now(),
             _unique_handle(conn, email or username)),
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
            "SELECT id, username, handle, full_name, role, email, email_verified, created_at FROM users "
            "WHERE deleted_at IS NULL ORDER BY created_at"
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
