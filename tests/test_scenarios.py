"""One test per case in the brief: each runs through the real API against the sample pack."""
from datetime import date

from app.db import db


def _load(client):
    r = client.post("/api/demo/load")
    assert r.status_code == 200, r.text
    return {item["email"]: item for item in r.json()["processed"]}


def _client_by_code(client, code):
    return next(c for c in client.get("/api/clients").json() if c["code"] == code)


def _approve_and_send(client, draft_id):
    assert client.post(f"/api/messages/{draft_id}/approve", json={"staff": "Priya"}).status_code == 200
    return client.post(f"/api/messages/{draft_id}/send",
                       json={"staff": "Priya", "channel": "email", "confirmed": True})


def _pending_draft(client, client_id):
    return next(m for m in client.get(f"/api/clients/{client_id}").json()["messages"] if m["status"] == "pending_approval")


def test_all_six_emails_process_with_no_server_errors(client):
    processed = _load(client)
    assert len(processed) == 6
    assert len(client.get("/api/clients").json()) == 4  # Rohan, Sunita, Amit, Priya


def test_rohan_is_missing_only_the_bank_statement(client):
    _load(client)
    rohan = _client_by_code(client, "C001")
    assert rohan["status"] == "docs_pending" and rohan["missing"] == ["Bank statement"]


def test_blurry_scan_is_enhanced_and_read_not_rejected(client):
    """Blur alone is never a rejection. The scan is enhanced and read; an unreadable number is held for staff."""
    processed = _load(client)
    doc = processed["Email 4 (duplicate)"]["documents"][0]
    assert doc["status"] != "rejected"
    assert doc["status"] in ("needs_verification", "accepted_needs_review")
    assert "blurry" in doc["reason"]
    rohan = client.get("/api/clients/1").json()
    blurry = next(d for d in rohan["documents"] if d["filename"] == "sample_pan_rohan_blurry.png")
    assert blurry["fields"].get("pan") is None  # no PAN number guessed from the blurred scan
    assert any(r["kind"] == "verify_document" and "sample_pan_rohan_blurry" in r["message"]
               for r in rohan["review_items"])


def test_blurry_scan_does_not_count_toward_the_checklist_until_staff_confirm(client):
    _load(client)
    rohan = client.get("/api/clients/1").json()
    pan_item = next(i for i in rohan["checklist"] if i["key"] == "pan")
    assert pan_item["state"] == "received"  # the clean PAN card from Email 1 is still on file


def test_duplicate_email_links_to_existing_client_not_a_second_record(client):
    processed = _load(client)
    assert processed["Email 4 (duplicate)"]["outcome"] == "linked_by_email"
    assert processed["Email 4 (duplicate)"]["client_id"] == 1
    assert len(client.get("/api/clients").json()) == 4


def test_reprocessing_the_same_email_changes_nothing(client):
    _load(client)
    before = client.get("/api/clients/1").json()["documents"]
    again = client.post("/api/sample-emails/3/process", json={"actor": "test"})
    assert again.status_code == 200 and again.json()["already_processed"] is True
    assert client.get("/api/clients/1").json()["documents"] == before


def test_wrong_document_is_rejected_and_client_is_told(client):
    processed = _load(client)
    doc = processed["Email 5 (wrong doc)"]["documents"][0]
    assert doc["status"] == "rejected" and "electricity bill" in doc["reason"]
    draft = _pending_draft(client, 1)
    assert "electricity bill" in draft["body"].lower()
    assert "Please send a PAN card or Aadhaar" in draft["body"]


def test_invalid_pan_is_rejected_and_client_stays_pending(client):
    _load(client)
    amit = client.get("/api/clients/3").json()
    assert amit["status"] == "docs_pending"
    assert any(d["status"] == "rejected" and "PAN must be" in d["reason"] for d in amit["documents"])
    assert "PAN must be" in _pending_draft(client, 3)["body"]


def test_gstin_carrying_another_clients_pan_is_raised_for_review(client):
    _load(client)
    review = client.get("/api/review").json()
    conflicts = [r for r in review if r["kind"] == "identity_conflict"]
    assert conflicts and conflicts[0]["code"] == "C002" and "C001" in conflicts[0]["message"]


def test_low_confidence_bank_holder_is_sent_to_review(client):
    _load(client)
    review = client.get("/api/review").json()
    assert any(r["kind"] == "verify_field" and r["code"] == "C002" for r in review)


def test_shared_email_with_different_pan_creates_separate_client(client):
    """Two people share one mailbox. A PAN that matches nobody must not be merged into the mailbox's client."""
    _load(client)
    from app.config import SAMPLE_ATTACHMENTS_DIR
    from app.emails import EmailIn
    from app.pipeline import process_email
    with db() as conn:
        conn.execute("UPDATE clients SET pan = NULL WHERE id = 1")  # Rohan's PAN is no longer on file
        conn.execute(
            "INSERT INTO clients (id, code, name, pan, email, service, created_at) "
            "VALUES (99, 'C099', 'Other Person', 'QQQQQ1111Q', 'shared@example.com', 'ITR', '2026-11-01T00:00:00+00:00')"
        )
        email = EmailIn(key="test-shared", sender="shared@example.com", body="I need ITR",
                        attachments=["sample_pan_rohan.png"])
        files = [(name, SAMPLE_ATTACHMENTS_DIR / name) for name in email.attachments]
        result = process_email(conn, email, files, "test")
    assert result["outcome"] == "created_shared_email"
    assert result["client_id"] != 99
    kinds = [r["kind"] for r in client.get("/api/review").json()]
    assert "shared_email" in kinds


def test_onboarding_is_refused_while_documents_or_reviews_are_open(client):
    _load(client)
    r = client.post("/api/clients/1/onboard", json={"staff": "Priya"})
    assert r.status_code == 409 and "Cannot onboard" in r.json()["error"]


def test_reminder_is_drafted_only_after_the_set_number_of_days(client):
    _load(client)
    # Approve Rohan's documents-needed draft and confirm it was sent, so the last contact is today.
    draft = _pending_draft(client, 1)
    assert _approve_and_send(client, draft["id"]).status_code == 200
    today = date.today().isoformat()
    none_yet = client.post("/api/reminders/run", json={"staff": "scheduler", "as_of": today}).json()
    assert none_yet["drafts_created"] == []
    from datetime import timedelta
    later = (date.today() + timedelta(days=3)).isoformat()
    due = client.post("/api/reminders/run", json={"staff": "scheduler", "as_of": later}).json()
    assert len(due["drafts_created"]) == 1
    assert "reminder" in client.get("/api/clients/1").json()["messages"][0]["subject"].lower()
