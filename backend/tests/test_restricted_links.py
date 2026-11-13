"""Restricted cross-case notices and the access-request flow between investigators."""
import json

from app import config
from helpers import new_case, upload


def _alerts(client, user, case_id):
    return client.get(f"/api/cases/{case_id}/cross-case-alerts", headers=user["headers"]).json()["alerts"]


def _restricted(client, user, case_id):
    return [a for a in _alerts(client, user, case_id) if not a["visible"]]


def _audit_actions(client, user, case_id):
    rows = client.get(f"/api/cases/{case_id}/audit", headers=user["headers"]).json()
    rows = rows.get("events", rows) if isinstance(rows, dict) else rows
    return [r["action"] for r in rows]


def test_both_sides_get_a_notice_without_details(client, make_user):
    a, b = make_user("Investigator A"), make_user("Investigator B")
    ca = new_case(client, a["headers"], "Warehouse theft RL1")
    cb = new_case(client, b["headers"], "Online scam RL1")
    upload(client, a["headers"], ca, "seller_note_a.txt", b"seller asked to transfer to SA4420000001234567890001 today please")
    upload(client, b["headers"], cb, "victim_note_b.txt", b"victim paid 2400 to SA4420000001234567890001 for a generator")

    ra = _restricted(client, a, ca)
    rb = _restricted(client, b, cb)
    assert len(ra) == 1 and len(rb) == 1
    assert ra[0]["reasons"][0]["type"] == "SHARED_IBAN"
    assert ra[0]["reasons"][0]["value"] == "SA4420000001234567890001"   # A's own value only
    # nothing from the other side leaks: no case id/name, no file name, no owner
    dumped_a, dumped_b = json.dumps(ra), json.dumps(rb)
    assert "Online scam RL1" not in dumped_a and "victim_note_b" not in dumped_a and "Investigator B" not in dumped_a
    assert "Warehouse theft RL1" not in dumped_b and "seller_note_a" not in dumped_b and "Investigator A" not in dumped_b
    assert "other_case_id" not in ra[0] and "other_evidence_id" not in ra[0]
    # the first sighting is sealed in each side's custody chain, once
    _alerts(client, a, ca)
    assert _audit_actions(client, a, ca).count("RESTRICTED_LINK_DETECTED") == 1
    assert client.get(f"/api/cases/{ca}/verify", headers=a["headers"]).json()["intact"] is True


def test_request_approve_turns_the_notice_into_a_full_link(client, make_user):
    a, b, c = make_user("Req A"), make_user("Owner B"), make_user("Stranger C")
    ca = new_case(client, a["headers"], "Case of A RL2")
    cb = new_case(client, b["headers"], "Case of B RL2")
    data = b"CCTV still exported 2026-09-13 cam 04 yard RL2"
    upload(client, a["headers"], ca, "still_a.jpg.txt", data)
    upload(client, b["headers"], cb, "still_b.jpg.txt", data)           # identical file
    link = _restricted(client, a, ca)[0]
    assert link["type"] == "IDENTICAL_FILE" and link["request_status"] is None

    # a stranger cannot use A's link id; the response looks like "no such link"
    r = client.post(f"/api/restricted-links/{link['link_id']}/request-access", headers=c["headers"], json={})
    assert r.status_code == 404

    r = client.post(f"/api/restricted-links/{link['link_id']}/request-access", headers=a["headers"],
                    json={"note": "Same CCTV still in my theft case"})
    assert r.status_code == 201, r.text
    req_id = r.json()["id"]
    dup = client.post(f"/api/restricted-links/{link['link_id']}/request-access", headers=a["headers"], json={})
    assert dup.status_code == 400 and dup.json()["detail"] == "ALREADY_REQUESTED"
    assert _restricted(client, a, ca)[0]["request_status"] == "PENDING"

    # the requester's outgoing list shows status only, never the target case
    out = client.get("/api/access-requests", headers=a["headers"]).json()["outgoing"]
    assert out[0]["status"] == "PENDING" and "Case of B RL2" not in json.dumps(out)

    # the owner sees who asks, from which case, which of THEIR files matched, and the note
    inc = client.get("/api/access-requests", headers=b["headers"]).json()["incoming"]
    mine = [x for x in inc if x["id"] == req_id][0]
    assert mine["requester_case_name"] == "Case of A RL2" and mine["target_case_name"] == "Case of B RL2"
    assert mine["matched_files"] == ["still_b.jpg.txt"] and mine["note"] == "Same CCTV still in my theft case"
    assert "ACCESS_REQUEST_RECEIVED" in _audit_actions(client, b, cb)

    # only the owner may decide
    assert client.post(f"/api/access-requests/{req_id}/approve", headers=a["headers"]).status_code == 404
    assert client.post(f"/api/access-requests/{req_id}/approve", headers=c["headers"]).status_code == 404
    r = client.post(f"/api/access-requests/{req_id}/approve", headers=b["headers"])
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    assert client.post(f"/api/access-requests/{req_id}/decline", headers=b["headers"]).status_code == 400

    # A is now a member: the link is a normal, fully visible alert and the case opens
    al = _alerts(client, a, ca)
    assert any(x["visible"] and x["other_case_id"] == cb for x in al)
    assert not any(not x["visible"] for x in al)
    assert client.get(f"/api/cases/{cb}", headers=a["headers"]).status_code == 200
    acts = _audit_actions(client, b, cb)
    assert "ACCESS_REQUEST_APPROVED" in acts and "MEMBER_ADDED" in acts
    assert client.get(f"/api/cases/{cb}/verify", headers=b["headers"]).json()["intact"] is True


def test_decline_keeps_the_case_closed(client, make_user):
    a, b = make_user("Req D"), make_user("Owner D")
    ca, cb = new_case(client, a["headers"], "A RL3"), new_case(client, b["headers"], "B RL3")
    upload(client, a["headers"], ca, "a.txt", b"contact sales.rl3@gmail.com about the invoice RL3")
    upload(client, b["headers"], cb, "b.txt", b"the supplier wrote from sales.rl3@gmail.com again")
    link = _restricted(client, a, ca)[0]
    req_id = client.post(f"/api/restricted-links/{link['link_id']}/request-access", headers=a["headers"], json={}).json()["id"]
    assert client.post(f"/api/access-requests/{req_id}/decline", headers=b["headers"]).json()["status"] == "DECLINED"
    assert client.get(f"/api/cases/{cb}", headers=a["headers"]).status_code == 404
    again = _restricted(client, a, ca)[0]
    assert again["request_status"] == "DECLINED" and "B RL3" not in json.dumps(again)
    assert "ACCESS_REQUEST_DECLINED" in _audit_actions(client, b, cb)


def test_fuzzy_signals_never_cross_the_case_boundary(client, make_user):
    a, b = make_user("Fuzzy A"), make_user("Fuzzy B")
    ca, cb = new_case(client, a["headers"], "A RL4"), new_case(client, b["headers"], "B RL4")
    # very similar wording and a shared URL, but no identical file and no phone/e-mail/IBAN
    upload(client, a["headers"], ca, "a.txt", b"The suspect drove a white pickup to the eastern warehouse gate at night. https://rl4.example/x")
    upload(client, b["headers"], cb, "b.txt", b"The suspect drove a white pickup to the eastern warehouse gate at dawn. https://rl4.example/x")
    assert _restricted(client, a, ca) == [] and _restricted(client, b, cb) == []


def test_notices_can_be_switched_off(client, make_user, monkeypatch):
    a, b = make_user("Off A"), make_user("Off B")
    ca, cb = new_case(client, a["headers"], "A RL5"), new_case(client, b["headers"], "B RL5")
    upload(client, a["headers"], ca, "a.txt", b"identical payload RL5 for both cases")
    upload(client, b["headers"], cb, "b.txt", b"identical payload RL5 for both cases")
    monkeypatch.setattr(config, "RESTRICTED_LINK_ALERTS", False)
    assert _restricted(client, a, ca) == []
    monkeypatch.setattr(config, "RESTRICTED_LINK_ALERTS", True)
    link = _restricted(client, a, ca)[0]
    monkeypatch.setattr(config, "RESTRICTED_LINK_ALERTS", False)
    r = client.post(f"/api/restricted-links/{link['link_id']}/request-access", headers=a["headers"], json={})
    assert r.status_code == 404


def test_deleted_evidence_or_case_stops_the_notice(client, make_user):
    a, b = make_user("Del A"), make_user("Del B")
    ca, cb = new_case(client, a["headers"], "A RL6"), new_case(client, b["headers"], "B RL6")
    upload(client, a["headers"], ca, "a.txt", b"identical payload RL6 for both cases")
    ev_b = upload(client, b["headers"], cb, "b.txt", b"identical payload RL6 for both cases").json()["id"]
    assert len(_restricted(client, a, ca)) == 1
    assert client.delete(f"/api/evidence/{ev_b}", headers=b["headers"]).status_code in (200, 204)
    assert _restricted(client, a, ca) == []
