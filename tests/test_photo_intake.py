"""Create a client from a photo. The app suggests; staff decide; an existing PAN is never created twice."""
from app.config import SAMPLE_ATTACHMENTS_DIR, SAMPLE_DIR

UNSEEN = SAMPLE_DIR / "unseen_layouts"


def _read(client, *paths, staff="Priya"):
    files = [("files", (p.name, p.read_bytes(), "image/png")) for p in paths]
    return client.post("/api/photo-intake", data={"staff": staff}, files=files)


def _decide(client, draft_id, **body):
    payload = {"staff": "Priya", "decision": "create", "service": "ITR"}
    payload.update(body)
    return client.post(f"/api/photo-intake/{draft_id}/decision", json=payload)


def test_clean_pan_photo_is_suggested_for_creation_and_creates_the_client_on_staff_decision(client):
    proposal = _read(client, UNSEEN / "unseen_pan_permanent_account_number.png").json()
    assert proposal["fields"]["pan"] == "BCDPN5678K" and proposal["fields"]["name"] == "Priya Nair"
    assert proposal["recommendation"]["action"] == "create"
    assert client.get("/api/clients").json() == []  # reading alone creates nothing
    r = _decide(client, proposal["draft_id"], name="Priya Nair", pan="BCDPN5678K")
    assert r.status_code == 200 and r.json()["outcome"] == "created"
    created = client.get("/api/clients").json()
    assert len(created) == 1 and created[0]["pan"] == "BCDPN5678K"
    assert [d["doc_type"] for d in r.json()["documents"]] == ["pan"]  # the photo is kept on the client


def test_pan_already_on_file_is_marked_already_exists_and_no_second_client_is_made(client):
    first = _read(client, UNSEEN / "unseen_pan_permanent_account_number.png").json()
    _decide(client, first["draft_id"], name="Priya Nair", pan="BCDPN5678K")
    again = _read(client, UNSEEN / "unseen_pan_permanent_account_number.png").json()
    assert again["recommendation"]["action"] == "already_exists"
    assert again["existing"]["code"] == "C001"
    r = _decide(client, again["draft_id"], name="Priya Nair", pan="BCDPN5678K")
    assert r.json()["outcome"] == "already_exists" and r.json()["code"] == "C001"
    assert len(client.get("/api/clients").json()) == 1


def test_blurry_photo_is_read_but_the_number_is_not_guessed_and_staff_must_check(client):
    proposal = _read(client, SAMPLE_ATTACHMENTS_DIR / "sample_pan_rohan_blurry.png").json()
    assert proposal["files"][0]["blurry"] is True
    assert proposal["fields"]["pan"] is None
    assert proposal["recommendation"]["action"] == "check"  # not create, and not thrown away either
    assert "type the details in" in proposal["recommendation"]["headline"]


def test_wrong_document_photo_is_suggested_for_disqualification_and_disqualifying_creates_nothing(client):
    proposal = _read(client, SAMPLE_ATTACHMENTS_DIR / "sample_wrong_document_electricity_bill.png").json()
    assert proposal["recommendation"]["action"] == "disqualify"
    assert any("electricity bill" in r for r in proposal["recommendation"]["reasons"])
    r = _decide(client, proposal["draft_id"], decision="disqualify", note="Wrong document")
    assert r.json()["outcome"] == "disqualified"
    assert client.get("/api/clients").json() == []


def test_similar_name_needs_staff_to_confirm_it_is_a_different_person(client):
    client.post("/api/clients", json={"staff": "Priya", "name": "Priya Nair", "service": "ITR"})
    proposal = _read(client, UNSEEN / "unseen_pan_permanent_account_number.png").json()
    assert proposal["recommendation"]["action"] == "check"
    assert proposal["similar"] and proposal["similar"][0]["code"] == "C001"
    blocked = _decide(client, proposal["draft_id"], name="Priya Nair", pan="BCDPN5678K")
    assert blocked.status_code == 409 and "similar name" in blocked.json()["error"]
    assert len(client.get("/api/clients").json()) == 1
    ok = _decide(client, proposal["draft_id"], name="Priya Nair", pan="BCDPN5678K", confirm_similar=True)
    assert ok.json()["outcome"] == "created" and len(client.get("/api/clients").json()) == 2


def test_aadhaar_photo_is_read_and_stored_masked(client):
    proposal = _read(client, UNSEEN / "unseen_aadhaar_aadhaar_no.png").json()
    assert proposal["fields"]["aadhaar"] == "XXXX XXXX 6548"
    _decide(client, proposal["draft_id"], name="Priya Nair")
    assert "4321 0987 6548" not in client.get("/api/clients/1").text


def test_a_reading_can_be_decided_only_once_and_unknown_ids_are_refused(client):
    proposal = _read(client, UNSEEN / "unseen_pan_permanent_account_number.png").json()
    assert _decide(client, proposal["draft_id"], name="Priya Nair", pan="BCDPN5678K").status_code == 200
    assert _decide(client, proposal["draft_id"], name="Priya Nair", pan="BCDPN5678K").status_code == 409
    assert _decide(client, "doesnotexist", name="X").status_code == 404


def test_no_photo_or_no_name_is_refused_with_a_clear_message(client):
    r = client.post("/api/photo-intake", data={"staff": "Priya"}, files=[("files", ("x.png", b"", "image/png"))])
    assert r.status_code in (400, 422)
    r = client.post("/api/photo-intake", data={"staff": ""}, files=[("files", ("x.png", b"abc", "image/png"))])
    assert r.status_code == 400
