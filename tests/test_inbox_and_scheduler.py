"""Real .eml uploads, the inbox folder, and the automatic reminder check."""
import email.message
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from app import main as app_main
from app import scheduler
from app.db import db


def _eml(message_id="<inbox-1@test.example>", sender="meena@example.com", body="Hi, I'm Meena Iyer. Need ITR.",
         attach=None, attach_name="meena_pan.png"):
    msg = email.message.EmailMessage()
    msg["From"] = f"Meena Iyer <{sender}>"
    msg["To"] = "office@example.com"
    msg["Subject"] = "Email 9 | ITR filing"
    msg["Date"] = format_datetime(datetime(2026, 11, 2, tzinfo=timezone.utc))
    msg["Message-ID"] = message_id
    msg.set_content(body)
    if attach:
        msg.add_attachment(attach, maintype="image", subtype="png", filename=attach_name)
    return bytes(msg)


def test_uploaded_eml_is_read_into_a_new_client(client):
    raw = _eml()
    r = client.post("/api/intake/eml", files=[("files", ("meena.eml", raw, "message/rfc822"))])
    assert r.status_code == 200
    result = r.json()["results"][0]
    assert result["outcome"] == "created" and result["email"] == "Email 9"
    assert client.get("/api/clients").json()[0]["email"] == "meena@example.com"


def test_the_same_eml_uploaded_twice_is_read_once(client):
    raw = _eml(message_id="<twice@test.example>")
    client.post("/api/intake/eml", files=[("files", ("a.eml", raw, "message/rfc822"))])
    again = client.post("/api/intake/eml", files=[("files", ("a.eml", raw, "message/rfc822"))]).json()["results"][0]
    assert again["already_processed"] is True
    assert len(client.get("/api/clients").json()) == 1


def test_a_non_eml_file_and_a_broken_eml_are_refused_without_a_crash(client):
    r = client.post("/api/intake/eml", files=[
        ("files", ("notes.txt", b"hello", "text/plain")),
        ("files", ("broken.eml", b"\xff\x00 nothing useful", "message/rfc822")),
    ])
    assert r.status_code == 200
    outcomes = [item["outcome"] for item in r.json()["results"]]
    assert outcomes == ["skipped", "refused"]


def test_inbox_folder_is_read_and_files_are_not_read_twice(client, tmp_path, monkeypatch):
    monkeypatch.setattr(app_main, "INBOX_DIR", tmp_path)
    (tmp_path / "01.eml").write_bytes(_eml(message_id="<inbox-a@test.example>", sender="a@example.com"))
    (tmp_path / "02.eml").write_bytes(_eml(message_id="<inbox-b@test.example>", sender="b@example.com"))
    first = client.post("/api/intake/inbox").json()
    assert first["files_found"] == 2 and all(r["outcome"] == "created" for r in first["results"])
    second = client.post("/api/intake/inbox").json()
    assert all(r["already_processed"] for r in second["results"])
    assert len(client.get("/api/clients").json()) == 2


def test_inbox_file_with_a_real_attachment_stores_the_document(client, tmp_path, monkeypatch):
    from app.config import SAMPLE_ATTACHMENTS_DIR
    monkeypatch.setattr(app_main, "INBOX_DIR", tmp_path)
    pan = (SAMPLE_ATTACHMENTS_DIR / "sample_pan_rohan.png").read_bytes()
    # The OCR cache is keyed by file name, so this uses the sample name; real Tesseract works with any name.
    (tmp_path / "rohan.eml").write_bytes(_eml(message_id="<inbox-pan@test.example>", sender="rohan@example.com",
                                              attach=pan, attach_name="sample_pan_rohan.png"))
    result = client.post("/api/intake/inbox").json()["results"][0]
    doc = result["documents"][0]
    assert doc["doc_type"] == "pan" and doc["status"] == "accepted_needs_review"  # the sample PAN has a known warning


def test_scheduler_is_off_in_tests_so_results_are_predictable(client):
    assert scheduler.start() is None
    assert scheduler.state["enabled"] is False


def test_automatic_check_drafts_reminders_for_old_clients_and_sends_nothing(client):
    client.post("/api/demo/load")
    # Rohan's missing-documents draft is still open. Close it, because the check never adds a second open draft.
    open_draft = next(m for m in client.get("/api/clients/1").json()["messages"] if m["status"] == "pending_approval")
    client.post(f"/api/messages/{open_draft['id']}/reject", json={"staff": "Priya", "note": "superseded in test"})
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(timespec="seconds")
    with db() as conn:
        conn.execute("UPDATE clients SET created_at = ? WHERE id = 1", (old,))
    created = scheduler.run_once()
    assert created == 1
    reminder = next(m for m in client.get("/api/clients/1").json()["messages"] if m["kind"] == "reminder")
    assert reminder["status"] == "pending_approval"          # a draft, waiting for a person
    assert client.get("/api/outbox").json() == []            # nothing sent
    assert scheduler.run_once() == 0                         # one open draft at a time: no duplicates
    assert scheduler.state["last_run"] is not None
