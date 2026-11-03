"""One test per failure case in the brief. The name says the case in plain words.

Each test shows the expected result the brief asks for. If a test fails, the README table
(section 5, "Failure cases and the test that checks each one") says what should have happened.
"""
from app.db import db


def _load(client):
    r = client.post("/api/demo/load")
    assert r.status_code == 200
    return {item["email"]: item for item in r.json()["processed"]}


def _pending(client, client_id):
    return next(m for m in client.get(f"/api/clients/{client_id}").json()["messages"] if m["status"] == "pending_approval")


def test_case_invalid_pan_is_rejected_with_the_reason_and_the_client_is_asked_again(client):
    processed = _load(client)
    doc = processed["Email 3"]["documents"][0]
    assert doc["status"] == "rejected" and "PAN must be 5 letters, 4 digits and 1 letter" in doc["reason"]
    assert "PAN must be" in _pending(client, 3)["body"]


def test_case_blurry_scan_is_enhanced_and_not_rejected_for_blur_and_its_number_is_not_guessed(client):
    processed = _load(client)
    doc = processed["Email 4 (duplicate)"]["documents"][0]
    assert doc["status"] in ("needs_verification", "accepted_needs_review")
    rohan = client.get("/api/clients/1").json()
    blurry = next(d for d in rohan["documents"] if d["filename"] == "sample_pan_rohan_blurry.png")
    assert blurry["fields"].get("pan") is None


def test_case_duplicate_email_is_linked_and_no_second_client_is_created(client):
    processed = _load(client)
    assert processed["Email 4 (duplicate)"]["outcome"] == "linked_by_email"
    assert len(client.get("/api/clients").json()) == 4  # Rohan, Sunita, Amit, Priya: no second Rohan


def test_case_wrong_document_is_rejected_and_the_client_is_told_which_documents_are_accepted(client):
    processed = _load(client)
    doc = processed["Email 5 (wrong doc)"]["documents"][0]
    assert doc["status"] == "rejected" and "electricity bill" in doc["reason"]
    assert "Please send a PAN card or Aadhaar" in _pending(client, 1)["body"]


def test_case_gstin_that_carries_another_clients_pan_is_raised_for_review(client):
    _load(client)
    conflicts = [r for r in client.get("/api/review").json() if r["kind"] == "identity_conflict"]
    assert conflicts and "C001" in conflicts[0]["message"]


def test_case_low_confidence_bank_holder_name_is_sent_to_a_human(client):
    _load(client)
    assert any(r["kind"] == "verify_field" and r["code"] == "C002" for r in client.get("/api/review").json())


def test_case_same_email_with_a_different_pan_is_never_merged_into_the_other_client(client):
    """Brief: never merge two people silently. Covered in depth by test_scenarios; this is the headline check."""
    processed = _load(client)
    assert processed["Email 6 (new layouts)"]["client_id"] != 1  # Priya is not merged into Rohan


def test_case_message_cannot_be_sent_without_a_named_approval(client):
    _load(client)
    draft = _pending(client, 1)
    r = client.post(f"/api/messages/{draft['id']}/send", json={"staff": "Priya", "channel": "email", "confirmed": True})
    assert r.status_code == 403 and client.get("/api/outbox").json() == []


def test_case_approved_text_is_the_text_that_is_sent_so_an_edit_removes_approval(client):
    _load(client)
    draft = _pending(client, 1)
    client.post(f"/api/messages/{draft['id']}/approve", json={"staff": "Priya"})
    client.patch(f"/api/messages/{draft['id']}", json={"staff": "Priya", "body": "Changed after approval"})
    r = client.post(f"/api/messages/{draft['id']}/link", json={"staff": "Priya", "channel": "email"})
    assert r.status_code == 403


def test_case_a_client_with_open_review_items_cannot_be_marked_onboarded(client):
    _load(client)
    r = client.post("/api/clients/1/onboard", json={"staff": "Priya"})
    assert r.status_code == 409 and "Cannot onboard" in r.json()["error"]


def test_case_full_aadhaar_number_is_never_stored_anywhere_in_the_database(client):
    from app.config import DB_PATH
    _load(client)
    with db() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    raw = DB_PATH.read_bytes()
    assert b"4321 0987 6548" not in raw and b"432109876548" not in raw


def test_case_reminder_is_only_ever_a_draft_and_nothing_is_sent(client):
    _load(client)
    client.post("/api/reminders/run", json={"staff": "scheduler", "as_of": "2030-01-01"})
    assert client.get("/api/outbox").json() == []
