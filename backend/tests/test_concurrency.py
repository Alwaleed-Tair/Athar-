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
