"""Real OCR on uploaded files. Skipped automatically when Tesseract is not installed."""
import shutil

import pytest

from app.config import SAMPLE_ATTACHMENTS_DIR, SETTINGS

pytestmark = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract not installed")


@pytest.fixture
def real_ocr(monkeypatch):
    monkeypatch.setitem(SETTINGS, "ocr_engine", "tesseract")


def _upload(client, client_id, doc_type, filename, label=""):
    path = SAMPLE_ATTACHMENTS_DIR / filename
    with path.open("rb") as handle:
        return client.post(f"/api/clients/{client_id}/documents",
                           data={"doc_type": doc_type, "staff": "Priya", "label": label},
                           files={"files": (filename, handle, "application/octet-stream")})


def test_uploaded_pan_card_is_read_and_sets_client_pan(client, real_ocr):
    cid = client.post("/api/clients", json={"staff": "Priya", "name": "Rohan Mehta"}).json()["id"]
    r = _upload(client, cid, "pan", "sample_pan_rohan.png")
    assert r.status_code == 200
    detail = r.json()
    assert detail["pan"] == "ABCDE1234F"
    assert any(d["doc_type"] == "pan" and d["status"] == "accepted_needs_review" for d in detail["documents"])


def test_wrong_file_for_the_chosen_type_is_rejected(client, real_ocr):
    cid = client.post("/api/clients", json={"staff": "Priya", "name": "Rohan Mehta"}).json()["id"]
    detail = _upload(client, cid, "pan", "sample_wrong_document_electricity_bill.png").json()
    assert detail["documents"][-1]["status"] == "rejected"


def test_declared_type_mismatch_is_rejected_with_reason(client, real_ocr):
    cid = client.post("/api/clients", json={"staff": "Priya", "name": "Sunita Traders", "service": "GST"}).json()["id"]
    detail = _upload(client, cid, "pan", "sample_gst_sunita.png").json()
    last = detail["documents"][-1]
    assert last["status"] == "rejected" and "uploaded as a pan card" in last["reason"]


def test_bank_statement_pdf_is_read_and_low_confidence_flagged(client, real_ocr):
    cid = client.post("/api/clients", json={"staff": "Priya", "name": "Sunita Traders", "service": "GST"}).json()["id"]
    detail = _upload(client, cid, "bank_statement", "sample_bank_statement_sunita.pdf").json()
    assert detail["documents"][-1]["status"] == "accepted_needs_review"
    assert any(r["kind"] == "verify_field" for r in detail["review_items"])


def test_unsupported_file_type_is_refused_clearly(client):
    cid = client.post("/api/clients", json={"staff": "Priya", "name": "Test Person"}).json()["id"]
    r = client.post(f"/api/clients/{cid}/documents", data={"doc_type": "pan", "staff": "Priya"},
                    files={"files": ("notes.docx", b"hello", "application/octet-stream")})
    assert r.status_code == 400 and "not a supported file" in r.json()["error"]


def test_other_document_keeps_its_label(client):
    cid = client.post("/api/clients", json={"staff": "Priya", "name": "Test Person"}).json()["id"]
    detail = _upload(client, cid, "other", "sample_pan_rohan.png", label="Form 16").json()
    assert detail["documents"][-1]["doc_label"] == "Form 16"


def test_unseen_pan_layout_is_read_by_real_tesseract(client, real_ocr):
    from app.config import SAMPLE_DIR
    cid = client.post("/api/clients", json={"staff": "Priya", "name": "Priya Nair"}).json()["id"]
    path = SAMPLE_DIR / "unseen_layouts" / "unseen_pan_permanent_account_number.png"
    with path.open("rb") as handle:
        detail = client.post(f"/api/clients/{cid}/documents",
                             data={"doc_type": "pan", "staff": "Priya"},
                             files={"files": (path.name, handle, "application/octet-stream")}).json()
    assert detail["pan"] == "BCDPN5678K"


def test_email_6_is_read_end_to_end_by_real_tesseract(client, real_ocr):
    processed = client.post("/api/demo/load").json()["processed"]
    email6 = next(p for p in processed if p["email"] == "Email 6 (new layouts)")
    assert [d["status"] for d in email6["documents"]] == ["accepted"] * 4
