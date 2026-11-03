"""Documents in layouts the sample pack never used. Extraction must not depend on one exact layout."""
from app.config import SAMPLE_DIR

UNSEEN = SAMPLE_DIR / "unseen_layouts"


def _upload(client, client_id, doc_type, path):
    with path.open("rb") as handle:
        return client.post(f"/api/clients/{client_id}/documents",
                           data={"doc_type": doc_type, "staff": "Priya"},
                           files={"files": (path.name, handle, "application/octet-stream")})


def _client(client, name="Priya Nair"):
    return client.post("/api/clients", json={"staff": "Priya", "name": name, "service": "ITR"}).json()["id"]


def test_pan_worded_permanent_account_number_with_pan_no_label_is_read(client):
    cid = _client(client)
    detail = _upload(client, cid, "pan", UNSEEN / "unseen_pan_permanent_account_number.png").json()
    assert detail["pan"] == "BCDPN5678K"
    assert detail["documents"][-1]["status"] == "accepted"


def test_aadhaar_with_aadhaar_no_label_is_read_and_masked(client):
    cid = _client(client)
    detail = _upload(client, cid, "aadhaar", UNSEEN / "unseen_aadhaar_aadhaar_no.png").json()
    doc = detail["documents"][-1]
    assert doc["status"] == "accepted"
    assert "4321" not in str(doc["fields"]).replace("XXXX", "") or "6548" in str(doc["fields"])
    assert "XXXX XXXX 6548" in str(doc["fields"])  # only the last four digits are kept


def test_gst_with_gstin_no_label_is_read_and_its_embedded_pan_is_checked(client):
    cid = _client(client)
    _upload(client, cid, "pan", UNSEEN / "unseen_pan_permanent_account_number.png")
    detail = _upload(client, cid, "gst_certificate", UNSEEN / "unseen_gst_gstin_no.png").json()
    assert detail["documents"][-1]["status"] == "accepted"
    assert not any(r["kind"] == "identity_conflict" for r in detail["review_items"])  # PAN matches


def test_bank_statement_with_name_of_account_holder_label_is_read(client):
    cid = _client(client, "Nair Enterprises")
    detail = _upload(client, cid, "bank_statement", UNSEEN / "unseen_bank_name_of_account_holder.png").json()
    doc = detail["documents"][-1]
    assert doc["status"] == "accepted"
    assert doc["fields"]["account_holder"]["value"] == "Nair Enterprises"
    assert doc["fields"]["account_number"]["value"] == "XXXX7788"


def test_email_6_with_all_four_new_layouts_creates_one_client_and_flags_the_name_difference(client):
    processed = client.post("/api/demo/load").json()["processed"]
    email6 = next(p for p in processed if p["email"] == "Email 6 (new layouts)")
    assert email6["outcome"] == "created"
    assert [d["status"] for d in email6["documents"]] == ["accepted"] * 4
    priya = next(c for c in client.get("/api/clients").json() if c["name"] == "Priya Nair")
    assert priya["status"] == "ready_for_review"
    review = client.get(f"/api/clients/{priya['id']}").json()["review_items"]
    assert any(r["kind"] == "name_mismatch" and "Nair Enterprises" in r["message"] for r in review)
