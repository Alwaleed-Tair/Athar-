import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .. import audit, config, mailer, ratelimit
from ..database import get_conn
from ..deps import require_admin

router = APIRouter(prefix="/api", tags=["contact"])

CATEGORIES = {"INQUIRY", "TECHNICAL", "SUGGESTION", "OTHER"}
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class ContactRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=200)
    category: str
    subject: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=10, max_length=5000)
    website: str = Field(default="", max_length=200)  # honeypot: real users never fill it


@router.post("/contact", status_code=201)
def send_contact(body: ContactRequest, request: Request):
    """Open to signed-out visitors, so it is throttled per IP and has a
    honeypot field. The message is always stored; an e-mail notification is
    additionally sent only if SMTP is configured -- and the response says
    which of the two actually happened."""
    fwd = request.headers.get("x-forwarded-for", "")
    ip = (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown"))[:64]
    if not ratelimit.allow(f"contact:{ip}", 5, 3600):
        raise HTTPException(status_code=429, detail="TOO_MANY_ATTEMPTS")
    if body.website.strip():  # bot
        return {"status": "RECEIVED", "stored": True, "emailed": False}
    name = " ".join(body.name.split())
    email = body.email.strip()
    subject = " ".join(body.subject.split())
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="INVALID_EMAIL")
    if body.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="INVALID_CATEGORY")

    user_id = None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        from .. import security
        payload = security.decode_access_token(auth.split(" ", 1)[1].strip())
        if payload:
            user_id = int(payload["sub"])

    now = datetime.now(timezone.utc).strftime(config.TIMESTAMP_FORMAT)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO contact_messages (user_id, name, email, category, subject, message, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, name, email, body.category, subject, body.message.strip(), now),
        )
        conn.commit()
        msg_id = cur.lastrowid

    emailed = False
    if config.CONTACT_TO and mailer.is_configured():
        text = (f"New ATHAR contact message #{msg_id}\nFrom: {name} <{email}>\nCategory: {body.category}\n"
                f"Subject: {subject}\n\n{body.message.strip()}\n")
        emailed = mailer.send_mail(config.CONTACT_TO, f"[ATHAR contact] {subject}", text, reply_to=email) == "SENT"
        if emailed:
            with get_conn() as conn:
                conn.execute("UPDATE contact_messages SET emailed = 1 WHERE id = ?", (msg_id,))
                conn.commit()
    return {"status": "RECEIVED", "stored": True, "emailed": emailed}


@router.get("/contact/messages")
def list_contact_messages(admin: dict = Depends(require_admin)):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM contact_messages ORDER BY created_at DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]


@router.post("/contact/messages/{message_id}/handled")
def mark_handled(message_id: int, admin: dict = Depends(require_admin)):
    with get_conn() as conn:
        cur = conn.execute("UPDATE contact_messages SET handled = 1 WHERE id = ?", (message_id,))
        conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": message_id, "handled": True}
