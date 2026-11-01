import os
import sys
import tempfile
from pathlib import Path

# Isolated storage + deterministic config BEFORE the app is imported.
_TMP = tempfile.mkdtemp(prefix="athar-test-")
os.environ["ATHAR_STORAGE_DIR"] = _TMP
os.environ["ATHAR_ADMIN_USERNAME"] = "admin"
os.environ["ATHAR_ADMIN_PASSWORD"] = "Adm1n!Secret#1"
os.environ["ATHAR_JWT_SECRET"] = "test-secret-" + "x" * 40
os.environ.pop("ATHAR_AI_KEY", None)
os.environ.pop("ATHAR_SMTP_HOST", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from app import config, mailer, ratelimit
from app.database import init_db
from app.main import app
from helpers import SENT, login as _login

init_db()


@pytest.fixture(autouse=True)
def _mail_capture(monkeypatch):
    SENT.clear()

    def fake_send(to, subject, text_body, html_body=None, reply_to=None):
        SENT.append({"to": to, "subject": subject, "body": text_body})
        return "SENT"

    monkeypatch.setattr(mailer, "send_mail", fake_send)
    monkeypatch.setattr(mailer, "delivery_available", lambda: True)
    ratelimit.reset_all()
    yield


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin(client):
    return _login(client, "admin", "Adm1n!Secret#1")


_counter = {"n": 0}


@pytest.fixture
def make_user(client, admin):
    def _make(name="User"):
        _counter["n"] += 1
        email = f"user{_counter['n']}@gmail.com"
        pw = "Str0ng!Pass#9"
        r = client.post("/api/users", headers=admin,
                        json={"full_name": name, "username": email, "password": pw, "role": "INVESTIGATOR"})
        assert r.status_code == 201, r.text
        return {"id": r.json()["id"], "email": email, "password": pw, "headers": _login(client, email, pw)}
    return _make
