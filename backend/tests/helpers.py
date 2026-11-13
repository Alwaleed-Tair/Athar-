"""Shared helpers (kept out of conftest so tests and fixtures share ONE module instance)."""



def login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def new_case(client, headers, name="Case"):
    r = client.post("/api/cases", headers=headers, json={"name": name, "description": "d"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def upload(client, headers, case_id, name, content: bytes, **form):
    return client.post(f"/api/cases/{case_id}/evidence", headers=headers,
                       files={"file": (name, content, "application/octet-stream")}, data=form)


WHATSAPP = (
    "[31/12/23, 10:15:30 PM] Ahmed: where is the laptop IMG_1204.jpg\n"
    "[31/12/23, 10:16:02 PM] Khalid: at the warehouse, call 0501234567\n"
    "second line of the message\n"
    "[31/12/23, 10:17:00 PM] Messages and calls are end-to-end encrypted.\n"
).encode()
