"""Nothing leaves the system without a named staff approval."""
from app.db import db


def _first_draft(client, client_id=1):
    return next(m for m in client.get(f"/api/clients/{client_id}").json()["messages"] if m["status"] == "pending_approval")


def test_send_is_refused_before_approval_and_outbox_stays_empty(client):
    client.post("/api/demo/load")
    draft = _first_draft(client)
    r = client.post(f"/api/messages/{draft['id']}/send", json={"staff": "Priya", "channel": "email"})
    assert r.status_code == 403 and "not been approved" in r.json()["error"]
    assert client.get("/api/outbox").json() == []


def test_approval_requires_a_staff_name(client):
    client.post("/api/demo/load")
    draft = _first_draft(client)
    r = client.post(f"/api/messages/{draft['id']}/approve", json={"staff": "  "})
    assert r.status_code == 400


def test_approve_then_staff_confirms_the_send_and_it_is_recorded(client):
    client.post("/api/demo/load")
    draft = _first_draft(client)
    assert client.post(f"/api/messages/{draft['id']}/approve", json={"staff": "Priya"}).status_code == 200
    r = client.post(f"/api/messages/{draft['id']}/send", json={"staff": "Priya", "channel": "email", "confirmed": True})
    assert r.status_code == 200 and r.json()["mode"] == "staff_confirmed"
    outbox = client.get("/api/outbox").json()
    assert len(outbox) == 1 and outbox[0]["mode"] == "staff_confirmed" and outbox[0]["recipient"] == "rohan@example.com"


def test_confirm_is_refused_until_the_staff_member_ticks_it(client):
    client.post("/api/demo/load")
    draft = _first_draft(client)
    client.post(f"/api/messages/{draft['id']}/approve", json={"staff": "Priya"})
    r = client.post(f"/api/messages/{draft['id']}/send", json={"staff": "Priya", "channel": "email"})
    assert r.status_code == 400 and "tick" in r.json()["error"]
    assert client.get("/api/outbox").json() == []


def test_link_is_made_only_for_an_approved_draft(client):
    client.post("/api/demo/load")
    draft = _first_draft(client)
    r = client.post(f"/api/messages/{draft['id']}/link", json={"staff": "Priya", "channel": "email"})
    assert r.status_code == 403
    client.post(f"/api/messages/{draft['id']}/approve", json={"staff": "Priya"})
    r = client.post(f"/api/messages/{draft['id']}/link", json={"staff": "Priya", "channel": "email"})
    assert r.status_code == 200 and r.json()["url"].startswith("mailto:rohan%40example.com?subject=")
    assert client.get("/api/outbox").json() == []  # making a link sends nothing


def test_whatsapp_link_uses_the_country_code_and_the_approved_text(client):
    client.post("/api/demo/load")
    draft = _first_draft(client)
    client.post(f"/api/messages/{draft['id']}/approve", json={"staff": "Priya"})
    r = client.post(f"/api/messages/{draft['id']}/link", json={"staff": "Priya", "channel": "whatsapp"})
    assert r.status_code == 200
    assert r.json()["url"].startswith("https://wa.me/919876500001?text=")
    assert r.json()["recipient"] == "+919876500001"


def test_editing_an_approved_draft_removes_approval(client):
    client.post("/api/demo/load")
    draft = _first_draft(client)
    client.post(f"/api/messages/{draft['id']}/approve", json={"staff": "Priya"})
    assert client.patch(f"/api/messages/{draft['id']}", json={"staff": "Priya", "body": "Changed text"}).status_code == 200
    r = client.post(f"/api/messages/{draft['id']}/send", json={"staff": "Priya", "channel": "email"})
    assert r.status_code == 403  # the approved text is always the text that goes out


def test_whatsapp_is_refused_when_no_phone_is_on_file(client):
    client.post("/api/demo/load")
    draft = _first_draft(client, client_id=3)  # Amit: no phone in his email
    client.post(f"/api/messages/{draft['id']}/approve", json={"staff": "Priya"})
    r = client.post(f"/api/messages/{draft['id']}/link", json={"staff": "Priya", "channel": "whatsapp"})
    assert r.status_code == 409 and "No phone number" in r.json()["error"]


def test_every_decision_is_written_to_the_activity_log(client):
    client.post("/api/demo/load")
    draft = _first_draft(client)
    client.post(f"/api/messages/{draft['id']}/approve", json={"staff": "Priya"})
    client.post(f"/api/messages/{draft['id']}/send", json={"staff": "Priya", "channel": "email", "confirmed": True})
    actions = [e["action"] for e in client.get("/api/clients/1").json()["events"]]
    assert "message_approved" in actions and "message_sent_confirmed" in actions


def test_review_item_needs_a_real_note_to_close(client):
    client.post("/api/demo/load")
    item = client.get("/api/review").json()[0]
    r = client.post(f"/api/review/{item['id']}/resolve", json={"staff": "Priya", "action": "resolve", "note": "x"})
    assert r.status_code == 400
