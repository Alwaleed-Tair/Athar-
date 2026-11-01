import re
import sqlite3

from app import config
from helpers import SENT, login as _login


def _token_from_mail():
    m = re.search(r"\?verify=([A-Za-z0-9_\-]+)", SENT[-1]["body"])
    assert m, SENT[-1]["body"]
    return m.group(1)


def _register(client, email, name="New User", pw="Str0ng!Pass#9"):
    return client.post("/api/auth/register", json={"full_name": name, "username": email, "password": pw})


def test_register_requires_verification(client):
    r = _register(client, "reg1@gmail.com")
    assert r.status_code == 201
    assert r.json()["status"] == "VERIFICATION_REQUIRED" and "token" not in r.json()
    assert SENT and SENT[-1]["to"] == "reg1@gmail.com"
    # correct password but unverified -> no session
    login = client.post("/api/auth/login", json={"username": "reg1@gmail.com", "password": "Str0ng!Pass#9"})
    assert login.status_code == 403 and login.json()["detail"] == "EMAIL_NOT_VERIFIED"
    # verify, then login works
    v = client.post("/api/auth/verify-email", json={"token": _token_from_mail()})
    assert v.status_code == 200 and v.json()["status"] == "VERIFIED"
    assert client.post("/api/auth/login", json={"username": "reg1@gmail.com", "password": "Str0ng!Pass#9"}).status_code == 200


def test_register_validation(client):
    assert _register(client, "x@yahoo.com").status_code == 400          # domain not allowed
    assert _register(client, "weak1@gmail.com", pw="weakpass").status_code == 400
    assert _register(client, "reg1@gmail.com").status_code == 400       # duplicate


def test_token_single_use_invalid_and_expired(client):
    _register(client, "reg2@gmail.com")
    tok = _token_from_mail()
    assert client.post("/api/auth/verify-email", json={"token": "not-a-real-token-123"}).json()["detail"] == "TOKEN_INVALID"
    assert client.post("/api/auth/verify-email", json={"token": tok}).status_code == 200
    # second use of an already-verified account's token is harmless
    assert client.post("/api/auth/verify-email", json={"token": tok}).json()["status"] == "ALREADY_VERIFIED"

    _register(client, "reg3@gmail.com")
    tok3 = _token_from_mail()
    con = sqlite3.connect(str(config.DB_PATH))
    con.execute("UPDATE email_tokens SET expires_at = '2000-01-01T00:00:00.000000' WHERE token_hash IN "
                "(SELECT token_hash FROM email_tokens ORDER BY id DESC LIMIT 1)")
    con.commit(); con.close()
    r = client.post("/api/auth/verify-email", json={"token": tok3})
    assert r.status_code == 400 and r.json()["detail"] == "TOKEN_EXPIRED"
    # a new link can be requested, and it works; the old one is revoked
    n = len(SENT)
    assert client.post("/api/auth/resend-verification", json={"email": "reg3@gmail.com"}).status_code == 200
    assert len(SENT) == n + 1
    assert client.post("/api/auth/verify-email", json={"token": tok3}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"token": _token_from_mail()}).json()["status"] == "VERIFIED"


def test_resend_is_generic_and_throttled(client):
    a = client.post("/api/auth/resend-verification", json={"email": "ghost@gmail.com"})
    assert a.status_code == 200 and a.json()["status"] == "ACCEPTED"
    assert not any(m["to"] == "ghost@gmail.com" for m in SENT)          # nothing sent, same answer
    again = client.post("/api/auth/resend-verification", json={"email": "ghost@gmail.com"})
    assert again.status_code == 429


def test_unverified_token_cannot_use_api(client, admin):
    # even a validly signed token is refused while the account is unverified
    from app import security
    _register(client, "reg4@gmail.com")
    uid = sqlite3.connect(str(config.DB_PATH)).execute("SELECT id FROM users WHERE email='reg4@gmail.com'").fetchone()[0]
    forged = security.create_access_token(uid, "reg4@gmail.com", "INVESTIGATOR", 0)
    assert client.get("/api/cases", headers={"Authorization": f"Bearer {forged}"}).status_code == 403


def test_admin_can_manually_activate(client, admin):
    _register(client, "reg5@gmail.com")
    uid = sqlite3.connect(str(config.DB_PATH)).execute("SELECT id FROM users WHERE email='reg5@gmail.com'").fetchone()[0]
    assert client.post(f"/api/users/{uid}/verify", headers=admin).status_code == 200
    assert client.post("/api/auth/login", json={"username": "reg5@gmail.com", "password": "Str0ng!Pass#9"}).status_code == 200


def test_login_lockout_and_no_demo_password(client):
    for _ in range(config.LOGIN_MAX_FAILURES):
        assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    locked = client.post("/api/auth/login", json={"username": "admin", "password": "Adm1n!Secret#1"})
    assert locked.status_code == 429 and "Retry-After" in locked.headers


def test_old_demo_passwords_rejected(client):
    for pw in ("ChangeMe123!", "admin1234"):
        assert client.post("/api/auth/login", json={"username": "admin", "password": pw}).status_code == 401


def test_profile_update_and_change_password(client, make_user):
    u = make_user("Old Name")
    me = client.get("/api/auth/me", headers=u["headers"]).json()
    assert me["email"] == u["email"] and me["email_verified"] is True
    r = client.patch("/api/auth/me", headers=u["headers"], json={"full_name": "New Name"})
    assert r.status_code == 200 and r.json()["full_name"] == "New Name"
    assert client.patch("/api/auth/me", headers=u["headers"], json={"full_name": "x"}).status_code == 422

    bad = client.post("/api/auth/change-password", headers=u["headers"],
                      json={"current_password": "nope", "new_password": "N3w!Strong#Pass"})
    assert bad.status_code == 400 and bad.json()["detail"] == "CURRENT_PASSWORD_WRONG"
    weak = client.post("/api/auth/change-password", headers=u["headers"],
                       json={"current_password": u["password"], "new_password": "weak"})
    assert weak.status_code == 400
    ok = client.post("/api/auth/change-password", headers=u["headers"],
                     json={"current_password": u["password"], "new_password": "N3w!Strong#Pass"})
    assert ok.status_code == 200
    # the old session is dead, the returned one works, new password logs in
    assert client.get("/api/auth/me", headers=u["headers"]).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {ok.json()['token']}"}).status_code == 200
    assert client.post("/api/auth/login", json={"username": u["email"], "password": "N3w!Strong#Pass"}).status_code == 200


def test_profile_edit_cannot_target_other_user(client, make_user):
    a, b = make_user("A Person"), make_user("B Person")
    client.patch("/api/auth/me", headers=a["headers"], json={"full_name": "Changed A"})
    assert client.get("/api/auth/me", headers=b["headers"]).json()["full_name"] == "B Person"


def test_admin_endpoints_forbidden_for_investigators(client, make_user):
    u = make_user()
    assert client.get("/api/users", headers=u["headers"]).status_code == 403
    assert client.post("/api/users", headers=u["headers"],
                       json={"full_name": "Zed Zed", "username": "z@gmail.com", "password": "Str0ng!Pass#9", "role": "ADMIN"}).status_code == 403


def test_security_headers(client):
    r = client.get("/")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/auth/me").headers["cache-control"] == "no-store"
