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
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from app import config, ratelimit
from app.database import init_db
from app.main import app
from helpers import login as _login

init_db()


@pytest.fixture(autouse=True)
def _reset_limits():
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
