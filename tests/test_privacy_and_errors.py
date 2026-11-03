"""Sensitive values are masked everywhere, and bad input gives a clear message, never a crash."""
import json

from app.config import DB_PATH


def test_full_aadhaar_is_never_stored_or_returned(client):
    client.post("/api/demo/load")
    full = "1234 5678 9012"
    assert full.encode() not in DB_PATH.read_bytes()
    assert "123456789012".encode() not in DB_PATH.read_bytes()
    body = json.dumps(client.get("/api/clients/1").json())
    assert full not in body and "XXXX XXXX 9012" in body


def test_full_bank_account_number_is_not_stored(client):
    client.post("/api/demo/load")
    body = json.dumps(client.get("/api/clients/2").json())
    assert "XXXX1234" in body and "XXXXXX1234" not in body


def test_unknown_client_gives_404_json_not_a_crash(client):
    r = client.get("/api/clients/9999")
    assert r.status_code == 404 and "does not exist" in r.json()["error"]


def test_bad_sample_index_gives_404_json(client):
    r = client.post("/api/sample-emails/99/process", json={"actor": "x"})
    assert r.status_code == 404


def test_invalid_pan_edit_is_refused_and_not_saved(client):
    client.post("/api/demo/load")
    r = client.patch("/api/clients/3", json={"staff": "Priya", "pan": "NOPE"})
    assert r.status_code == 400 and "Not saved" in r.json()["error"]
    assert client.get("/api/clients/3").json()["pan"] is None


def test_pan_already_belonging_to_another_client_is_refused(client):
    client.post("/api/demo/load")
    r = client.patch("/api/clients/3", json={"staff": "Priya", "pan": "ABCDE1234F"})
    assert r.status_code == 409 and "C001" in r.json()["error"]


def test_intake_without_sender_is_a_clean_validation_error(client):
    r = client.post("/api/intake", data={"body": "hello"})
    assert r.status_code == 422


def test_frontend_and_health_are_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/app.js").status_code == 200
    assert client.get("/api/health").json()["ok"] is True
