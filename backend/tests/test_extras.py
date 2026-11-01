import io
import json
import re
import sqlite3

from PIL import Image

from app import analysis, config, embeddings
from helpers import SENT, new_case, upload


def _png():
    b = io.BytesIO(); Image.new("RGB", (40, 20), "white").save(b, "PNG"); return b.getvalue()


# ---- username (handle) ---------------------------------------------------------
def test_editable_username(client, make_user):
    a, b = make_user("Alice A"), make_user("Bob B")
    me = client.get("/api/auth/me", headers=a["headers"]).json()
    assert me["handle"] and "@" not in me["handle"]
    ok = client.patch("/api/auth/me", headers=a["headers"], json={"full_name": "Alice A", "handle": "alice.k"})
    assert ok.status_code == 200 and ok.json()["handle"] == "alice.k"
    assert client.patch("/api/auth/me", headers=b["headers"], json={"full_name": "Bob B", "handle": "ALICE.K"}).json()["detail"] == "HANDLE_TAKEN"
    assert client.patch("/api/auth/me", headers=b["headers"], json={"full_name": "Bob B", "handle": "a b"}).json()["detail"] == "INVALID_HANDLE"
    assert client.patch("/api/auth/me", headers=b["headers"], json={"full_name": "Bob B", "handle": "x"}).json()["detail"] == "INVALID_HANDLE"
    # the username can be used to sign in too
    assert client.post("/api/auth/login", json={"username": "alice.k", "password": a["password"]}).status_code == 200


# ---- password reset by e-mail ------------------------------------------------------
def _reset_token():
    return re.search(r"\?reset=([A-Za-z0-9_\-]+)", SENT[-1]["body"]).group(1)


def test_password_reset_by_email(client, make_user):
    u = make_user("Alice A")
    # unknown address: same answer, nothing sent
    n = len(SENT)
    assert client.post("/api/auth/forgot-password", json={"email": "ghost@gmail.com"}).json()["status"] == "ACCEPTED"
    assert len(SENT) == n
    assert client.post("/api/auth/forgot-password", json={"email": u["email"]}).status_code == 200
    assert len(SENT) == n + 1 and SENT[-1]["to"] == u["email"]
    tok = _reset_token()
    assert client.post("/api/auth/reset-password", json={"token": tok, "new_password": "weak"}).status_code == 400
    assert client.post("/api/auth/reset-password", json={"token": "x" * 20, "new_password": "N3w!Strong#Pass"}).json()["detail"] == "TOKEN_INVALID"
    assert client.post("/api/auth/reset-password", json={"token": tok, "new_password": "N3w!Strong#Pass"}).status_code == 200
    assert client.post("/api/auth/reset-password", json={"token": tok, "new_password": "N3w!Strong#Pass2"}).status_code == 400   # single use
    assert client.get("/api/auth/me", headers=u["headers"]).status_code == 401                                                   # old session ended
    assert client.post("/api/auth/login", json={"username": u["email"], "password": "N3w!Strong#Pass"}).status_code == 200
    assert client.post("/api/auth/login", json={"username": u["email"], "password": u["password"]}).status_code == 401


def test_reset_token_expires_and_is_not_a_verify_token(client, make_user):
    u = make_user("Alice A")
    client.post("/api/auth/forgot-password", json={"email": u["email"]})
    tok = _reset_token()
    assert client.post("/api/auth/verify-email", json={"token": tok}).status_code == 400      # purposes are separate
    con = sqlite3.connect(str(config.DB_PATH))
    con.execute("UPDATE email_tokens SET expires_at='2000-01-01T00:00:00.000000' WHERE purpose='RESET' AND used_at IS NULL")
    con.commit(); con.close()
    assert client.post("/api/auth/reset-password", json={"token": tok, "new_password": "N3w!Strong#Pass"}).json()["detail"] == "TOKEN_EXPIRED"


# ---- account deletion -----------------------------------------------------------------
def test_delete_account_transfers_archives_and_erases(client, make_user):
    a, b = make_user("Alice A"), make_user("Bob B")
    shared = new_case(client, a["headers"], "Shared")
    client.post(f"/api/cases/{shared}/members", headers=a["headers"], json={"email": b["email"]})
    solo = new_case(client, a["headers"], "Solo")
    ev = upload(client, a["headers"], solo, "s.txt", b"solo evidence text").json()
    client.post("/api/contact", headers=a["headers"], json={"name": "Alice A", "email": a["email"], "category": "OTHER", "subject": "hello there", "message": "a long enough message"})

    assert client.post("/api/auth/delete-account", headers=a["headers"], json={"password": "wrong"}).status_code == 400
    r = client.post("/api/auth/delete-account", headers=a["headers"], json={"password": a["password"]})
    assert r.status_code == 200 and r.json() == {"status": "DELETED", "cases_transferred": 1, "cases_archived": 1}
    assert client.get("/api/auth/me", headers=a["headers"]).status_code == 401
    assert client.post("/api/auth/login", json={"username": a["email"], "password": a["password"]}).status_code == 401
    # shared case handed to Bob, who can now manage it; solo case archived
    assert client.get(f"/api/cases/{shared}", headers=b["headers"]).json()["is_owner"] is True
    assert client.get(f"/api/cases/{solo}", headers=b["headers"]).status_code == 404
    con = sqlite3.connect(str(config.DB_PATH))
    row = con.execute("SELECT username,email,full_name,password_hash FROM users WHERE id=(SELECT uploaded_by FROM evidence WHERE id=?)", (ev["id"],)).fetchone()
    assert row[1] == "" and row[2] == "" and row[0].startswith("deleted-") and row[3] == "!"
    assert con.execute("SELECT COUNT(*) FROM contact_messages WHERE email=?", (a["email"],)).fetchone()[0] == 0
    assert con.execute("SELECT deleted_at FROM evidence WHERE id=?", (ev["id"],)).fetchone()[0]
    con.close()
    # the freed e-mail can register again; the audit chain still verifies
    assert client.post("/api/auth/register", json={"full_name": "Alice Again", "username": a["email"], "password": "Str0ng!Pass#9"}).status_code == 201
    assert client.get(f"/api/cases/{shared}/verify", headers=b["headers"]).json()["intact"] is True


def test_last_admin_cannot_delete(client, admin):
    r = client.post("/api/auth/delete-account", headers=admin, json={"password": "Adm1n!Secret#1"})
    assert r.status_code == 400 and r.json()["detail"] == "LAST_ADMIN"


# ---- OCR ------------------------------------------------------------------------------------
def test_ocr_disabled_is_honest(client, make_user, monkeypatch):
    monkeypatch.setattr(analysis, "tesseract_available", lambda: False)
    monkeypatch.setattr(config, "ATHAR_AI_KEY", None)
    a = make_user("Alice A"); cid = new_case(client, a["headers"])
    ev = upload(client, a["headers"], cid, "shot.png", _png()).json()
    r = client.post(f"/api/evidence/{ev['id']}/ocr", headers=a["headers"]).json()
    assert r["status"] == "DISABLED" and "text" not in r
    txt = upload(client, a["headers"], cid, "n.txt", b"plain text file").json()
    assert client.post(f"/api/evidence/{txt['id']}/ocr", headers=a["headers"]).status_code == 400
    other = make_user("Bob B")
    assert client.post(f"/api/evidence/{ev['id']}/ocr", headers=other["headers"]).status_code == 404


def test_ocr_via_vision_creates_searchable_text_and_conversation(client, make_user, monkeypatch):
    monkeypatch.setattr(analysis, "tesseract_available", lambda: False)
    monkeypatch.setattr(config, "ATHAR_AI_KEY", "dummy")
    monkeypatch.setattr(analysis, "_call_vision_model",
                        lambda *a, **k: ("خولة: وين الملف؟\nأحمد: عند المحل في الرياض\nخولة: تمام", "stop"))
    a = make_user("Alice A"); cid = new_case(client, a["headers"])
    ev = upload(client, a["headers"], cid, "chat_shot.png", _png()).json()
    r = client.post(f"/api/evidence/{ev['id']}/ocr", headers=a["headers"]).json()
    assert r["status"] == "SUCCESS" and r["method"] == "AI_VISION" and r["is_approximation"] is True
    assert r["conversation"] == {"format": "OCR_TEXT", "message_count": 3}
    got = client.get(f"/api/evidence/{ev['id']}", headers=a["headers"]).json()
    assert got["ocr"]["method"] == "OCR_AI_VISION" and got["conversation"]["message_count"] == 3
    hits = client.get("/api/search", headers=a["headers"], params={"q": "الرياض", "case_id": cid}).json()
    assert hits["evidence"] and hits["messages"]
    assert client.get(f"/api/evidence/{ev['id']}/conversation", headers=a["headers"]).json()["messages"][0]["source_ref"] == "ocr line 1"
    audit = client.get(f"/api/cases/{cid}/audit?lang=en", headers=a["headers"]).json()
    assert any(x["action"] == "EVIDENCE_OCR_RUN" for x in audit)
    assert client.get(f"/api/cases/{cid}/report", params={"lang": "en"}, headers=a["headers"]).status_code == 200


def test_ocr_tesseract_path(client, make_user, monkeypatch):
    import subprocess
    monkeypatch.setattr(analysis, "tesseract_available", lambda: True)
    monkeypatch.setattr("shutil.which", lambda n: "/usr/bin/tesseract")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, b"hello from tesseract", b""))
    a = make_user("Alice A"); cid = new_case(client, a["headers"])
    ev = upload(client, a["headers"], cid, "scan.png", _png()).json()
    r = client.post(f"/api/evidence/{ev['id']}/ocr", headers=a["headers"]).json()
    assert r["status"] == "SUCCESS" and r["method"] == "TESSERACT" and r["text"] == "hello from tesseract"


# ---- semantic search -------------------------------------------------------------------------
def test_semantic_search_disabled_then_enabled_and_scoped(client, make_user, monkeypatch):
    a, b = make_user("Alice A"), make_user("Bob B")
    ca, cb = new_case(client, a["headers"]), new_case(client, b["headers"])
    upload(client, a["headers"], ca, "car.txt", b"The suspect drove a red vehicle away from the bank")
    upload(client, a["headers"], ca, "food.txt", b"Recipe for rice with chicken and spices for dinner")
    upload(client, b["headers"], cb, "theirs.txt", b"A car was seen leaving the bank at night")
    monkeypatch.setattr(config, "EMBED_KEY", "")
    assert client.get("/api/search/semantic", headers=a["headers"], params={"q": "automobile"}).json()["status"] == "DISABLED"

    monkeypatch.setattr(config, "EMBED_KEY", "k")
    calls = []

    def fake_embed(texts):
        calls.append(texts)
        def vec(t):
            t = t.lower()
            return [1.0 if ("car" in t or "vehicle" in t or "automobile" in t) else 0.0,
                    1.0 if ("rice" in t or "recipe" in t) else 0.0, 0.05]
        return [vec(t) for t in texts]

    monkeypatch.setattr(embeddings, "_embed", fake_embed)
    r = client.get("/api/search/semantic", headers=a["headers"], params={"q": "automobile theft"}).json()
    assert r["status"] == "SUCCESS" and [x["filename"] for x in r["results"]] == ["car.txt"]
    sent = json.dumps(calls)
    assert "A car was seen leaving" not in sent                       # B's text never sent for A's search
    n = len(calls)
    client.get("/api/search/semantic", headers=a["headers"], params={"q": "automobile"})
    assert sum(len(c) for c in calls[n:]) == 1                          # vectors cached: only the query is embedded
    monkeypatch.setattr(embeddings, "_embed", lambda t: (_ for _ in ()).throw(embeddings.EmbeddingError("x")))
    assert client.get("/api/search/semantic", headers=a["headers"], params={"q": "anything new"}).json()["status"] == "FAILED"
