import io
import sqlite3

from pypdf import PdfReader

from app import config
from helpers import WHATSAPP, new_case, upload


def _pdf_text(data: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)


def test_report_en_ar_contents_and_audit(client, make_user):
    a = make_user("Alice A")
    cid = new_case(client, a["headers"], "Warehouse Theft")
    keep = upload(client, a["headers"], cid, "statement.txt", b"Witness statement about the Riyadh warehouse.", description="Signed statement").json()
    gone = upload(client, a["headers"], cid, "deleted-file.txt", b"this one will be deleted before export").json()
    chat = upload(client, a["headers"], cid, "chat.txt", WHATSAPP).json()
    client.delete(f"/api/evidence/{gone['id']}", headers=a["headers"])

    r = client.get(f"/api/cases/{cid}/report", params={"lang": "en"}, headers=a["headers"])
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and "attachment" in r.headers["content-disposition"]
    text = _pdf_text(r.content)
    assert "Warehouse Theft" in text and "statement.txt" in text and "chat.txt" in text
    assert keep["sha256"] in text.replace("\n", "").replace(" ", "")      # recorded hash is printed
    body, _, custody = text.partition("9. Chain of custody")
    assert "deleted-file.txt" not in body                                  # not in inventory/analysis sections
    assert "deleted-file.txt" in custody and "deleted evidence" in custody # immutable custody log still records it
    assert "AI ESTIMATE" in text and "No AI analysis has been run" in text # AI is separated & honest
    assert "intact" in text.lower() and "Ahmed" in text                    # chain status + conversation participants

    ar = client.get(f"/api/cases/{cid}/report", params={"lang": "ar"}, headers=a["headers"])
    assert ar.status_code == 200 and ar.content.startswith(b"%PDF") and len(ar.content) > 4000
    assert any(x["action"] == "REPORT_GENERATED" for x in client.get(f"/api/cases/{cid}/audit?lang=en", headers=a["headers"]).json())


def test_report_flags_tampered_file(client, make_user):
    a = make_user("Alice A")
    cid = new_case(client, a["headers"], "Tamper case")
    ev = upload(client, a["headers"], cid, "doc.txt", b"original content of the document").json()
    con = sqlite3.connect(str(config.DB_PATH))
    stored = con.execute("SELECT stored_name FROM evidence WHERE id=?", (ev["id"],)).fetchone()[0]
    con.close()
    (config.EVIDENCE_DIR / stored).write_bytes(b"changed")
    text = _pdf_text(client.get(f"/api/cases/{cid}/report", params={"lang": "en"}, headers=a["headers"]).content)
    assert "MISMATCH" in text and "do NOT match" in text


def test_report_shows_cached_ai_only_with_label(client, make_user):
    a = make_user("Alice A")
    cid = new_case(client, a["headers"], "AI case")
    ev = upload(client, a["headers"], cid, "doc.txt", b"some document content").json()
    con = sqlite3.connect(str(config.DB_PATH))
    con.execute("INSERT INTO case_summary (case_id, summary_text, lang, generated_at) VALUES (?, 'Draft summary text', 'en', '2026-01-01T00:00:00.000000')", (cid,))
    con.commit(); con.close()
    text = _pdf_text(client.get(f"/api/cases/{cid}/report", params={"lang": "en"}, headers=a["headers"]).content)
    assert "Draft summary text" in text and "automated estimate" in text
    assert "shown separately in section 8" in text


def test_contact_form(client, make_user):
    ok = {"name": "Sara Ali", "email": "sara@gmail.com", "category": "TECHNICAL",
          "subject": "Cannot upload", "message": "The upload button does nothing on mobile."}
    r = client.post("/api/contact", json=ok)
    assert r.status_code == 201 and r.json()["stored"] is True and r.json()["emailed"] is False   # no SMTP -> not claimed
    assert client.post("/api/contact", json={**ok, "email": "not-an-email"}).status_code == 400
    assert client.post("/api/contact", json={**ok, "category": "WHATEVER"}).status_code == 400
    assert client.post("/api/contact", json={**ok, "message": "short"}).status_code == 422
    assert client.post("/api/contact", json={**ok, "website": "http://spam"}).json()["stored"] is True  # honeypot silently dropped
    con = sqlite3.connect(str(config.DB_PATH))
    assert con.execute("SELECT COUNT(*) FROM contact_messages WHERE email='sara@gmail.com'").fetchone()[0] == 1
    con.close()
    u = make_user("Alice A")
    assert client.get("/api/contact/messages", headers=u["headers"]).status_code == 403


def test_contact_rate_limited(client):
    body = {"name": "Spam Bot", "email": "spam@gmail.com", "category": "OTHER", "subject": "hello there", "message": "this is a long enough message"}
    codes = [client.post("/api/contact", json=body).status_code for _ in range(7)]
    assert codes[:5] == [201] * 5 and codes[5] == 429


def test_report_download_link_flow(client, make_user, monkeypatch):
    from app.routers import reports as rp
    a, b = make_user("Alice A"), make_user("Bob B")
    cid = new_case(client, a["headers"], "Link case")
    upload(client, a["headers"], cid, "a.txt", b"link evidence text")
    assert client.post(f"/api/cases/{cid}/report-link", headers=b["headers"]).status_code == 404      # outsider
    link = client.post(f"/api/cases/{cid}/report-link", params={"lang": "ar"}, headers=a["headers"]).json()
    # a plain tap: NO Authorization header
    r1 = client.get(link["url"], params={"inline": "true"})
    assert r1.status_code == 200 and r1.content.startswith(b"%PDF") and r1.headers["content-disposition"].startswith("inline")
    r2 = client.get(link["url"])                                             # phones request again; still valid
    assert r2.status_code == 200 and r2.headers["content-disposition"].startswith("attachment") and r2.content == r1.content
    audit = client.get(f"/api/cases/{cid}/audit?lang=en", headers=a["headers"]).json()
    assert sum(1 for x in audit if x["action"] == "REPORT_GENERATED") == 1     # logged once per link
    assert client.get("/api/report-download/not-a-real-token").status_code == 404
    # link dies when the user loses access
    client.post(f"/api/cases/{cid}/members", headers=a["headers"], json={"email": b["email"]})
    l2 = client.post(f"/api/cases/{cid}/report-link", headers=b["headers"]).json()
    client.delete(f"/api/cases/{cid}/members/{b['id']}", headers=a["headers"])
    assert client.get(l2["url"]).status_code == 404
    # and expires
    l3 = client.post(f"/api/cases/{cid}/report-link", headers=a["headers"]).json()
    for v in rp._LINKS.values():
        v["exp"] = 0
    assert client.get(l3["url"]).status_code == 404
