from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from helpers import new_case, upload


def test_parallel_requests_have_no_errors_and_chain_stays_intact(client, make_user, admin):
    u = make_user("Alice A")
    cid = new_case(client, u["headers"], "Parallel")
    upload(client, u["headers"], cid, "a.txt", b"parallel evidence text")

    def hit(i):
        k = i % 6
        if k == 0:
            return client.get("/api/auth/me", headers=u["headers"]).status_code
        if k == 1:
            return client.get("/api/cases", headers=u["headers"]).status_code
        if k == 2:
            return client.get(f"/api/cases/{cid}", headers=u["headers"]).status_code      # writes an audit event
        if k == 3:
            return client.get(f"/api/cases/{cid}/evidence", headers=u["headers"]).status_code
        if k == 4:
            return client.post("/api/auth/login", json={"username": u["email"], "password": u["password"]}).status_code
        return client.get(f"/api/cases/{cid}/cross-case-alerts", headers=u["headers"]).status_code

    with ThreadPoolExecutor(16) as ex:
        codes = Counter(ex.map(hit, range(300)))
    assert codes == Counter({200: 300}), codes
    # concurrent audit appends must not fork or corrupt the hash chain
    assert client.get("/api/audit/verify-all", headers=admin).json()["intact"] is True
    assert client.get(f"/api/cases/{cid}/verify", headers=u["headers"]).json()["intact"] is True


def test_parallel_duplicate_registration_never_500(client):
    from app import ratelimit

    def reg(_):
        ratelimit.reset_all()
        return client.post("/api/auth/register", json={"full_name": "Race User", "username": "race1@gmail.com", "password": "Str0ng!Pass#9"}).status_code

    with ThreadPoolExecutor(8) as ex:
        codes = Counter(ex.map(reg, range(16)))
    assert codes[201] == 1 and codes[400] == 15 and 500 not in codes, codes


def test_parallel_uploads_all_succeed(client, make_user):
    u = make_user("Alice A")
    cid = new_case(client, u["headers"], "Uploads")
    with ThreadPoolExecutor(8) as ex:
        codes = Counter(ex.map(lambda i: upload(client, u["headers"], cid, f"f{i}.txt", f"parallel upload number {i}".encode()).status_code, range(24)))
    assert codes == Counter({201: 24}), codes
    assert len(client.get(f"/api/cases/{cid}/evidence", headers=u["headers"]).json()) == 24
    assert client.get(f"/api/cases/{cid}/verify", headers=u["headers"]).json()["intact"] is True
