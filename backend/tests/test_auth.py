import re
import sqlite3

from app import config
from helpers import login as _login


def _register(client, email, name="New User", pw="Str0ng!Pass#9"):
    return client.post("/api/auth/register", json={"full_name": name, "username": email, "password": pw})


def _uid(email):
    return sqlite3.connect(str(config.DB_PATH)).execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]


def test_register_creates_pending_account_without_session(client):
    r = _register(client, "reg1@gmail.com")
    assert r.status_code == 201 and r.json()["status"] == "PENDING_APPROVAL" and "token" not in r.json()
    login = client.post("/api/auth/login", json={"username": "reg1@gmail.com", "password": "Str0ng!Pass#9"})
    assert login.status_code == 403 and login.json()["detail"] == "PENDING_APPROVAL"
    # wrong password still looks like any wrong password (no account probing)
    assert client.post("/api/auth/login", json={"username": "reg1@gmail.com", "password": "nope"}).status_code == 401


def test_register_validation(client):
    assert _register(client, "x@yahoo.com").status_code == 400          # domain not allowed
    assert _register(client, "weak1@gmail.com", pw="weakpass").status_code == 400
    _register(client, "dupe1@gmail.com")
    assert _register(client, "dupe1@gmail.com").status_code == 400      # duplicate


def test_pending_token_cannot_use_api(client):
    from app import security
    _register(client, "reg4@gmail.com")
    forged = security.create_access_token(_uid("reg4@gmail.com"), "reg4@gmail.com", "INVESTIGATOR", 0)
    r = client.get("/api/cases", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 403 and r.json()["detail"] == "PENDING_APPROVAL"


def test_admin_sees_pending_requests_and_approves(client, admin, make_user):
    _register(client, "pend1@gmail.com", name="Pending One")
    pend = client.get("/api/users/pending", headers=admin).json()
    assert "pend1@gmail.com" in [u["email"] for u in pend]
    uid = _uid("pend1@gmail.com")
    assert client.post(f"/api/users/{uid}/approve", headers=admin).json()["approved"] is True
    assert "pend1@gmail.com" not in [u["email"] for u in client.get("/api/users/pending", headers=admin).json()]
    assert client.post("/api/auth/login", json={"username": "pend1@gmail.com", "password": "Str0ng!Pass#9"}).status_code == 200
    rows = client.get(f"/api/users", headers=admin).json()
    assert next(u for u in rows if u["email"] == "pend1@gmail.com")["email_verified"] is True
    # approval is recorded
    con = sqlite3.connect(str(config.DB_PATH))
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action='ACCOUNT_APPROVED'").fetchone()[0] >= 1
    con.close()
    # investigators cannot see or decide requests
    u = make_user("Normal One")
    assert client.get("/api/users/pending", headers=u["headers"]).status_code == 403
    assert client.post(f"/api/users/{uid}/approve", headers=u["headers"]).status_code == 403
    assert client.post(f"/api/users/{uid}/reject", headers=u["headers"]).status_code == 403


def test_admin_rejects_request_and_person_can_apply_again(client, admin):
    _register(client, "rej1@gmail.com")
    uid = _uid("rej1@gmail.com")
    assert client.post(f"/api/users/{uid}/reject", headers=admin).json()["rejected"] is True
    assert client.post("/api/auth/login", json={"username": "rej1@gmail.com", "password": "Str0ng!Pass#9"}).status_code == 401
    assert _register(client, "rej1@gmail.com").status_code == 201
    # an approved account can never be "rejected" away through this endpoint
    uid2 = _uid("rej1@gmail.com")
    client.post(f"/api/users/{uid2}/approve", headers=admin)
    assert client.post(f"/api/users/{uid2}/reject", headers=admin).status_code == 404


def test_email_features_are_gone(client):
    for path in ("/api/auth/verify-email", "/api/auth/resend-verification", "/api/auth/forgot-password", "/api/auth/reset-password"):
        assert client.post(path, json={}).status_code in (404, 405)


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
