"""Test examples: the five built-in sample cases, and examples that staff add themselves."""
from app import examples as ex


def test_six_builtin_eml_examples_are_listed_with_expected_results(client):
    items = client.get("/api/examples").json()
    builtin = [i for i in items if i["kind"] == "built-in"]
    assert len(builtin) == 6
    assert all(i["expected"] for i in builtin)
    assert all(i["file"].endswith(".eml") for i in builtin)
    assert {i["key"] for i in builtin} == {f"sample:{n}" for n in range(6)}


def test_running_a_builtin_example_is_idempotent(client):
    first = client.post("/api/examples/sample:0/run")
    assert first.status_code == 200 and first.json()["outcome"] == "created"
    again = client.post("/api/examples/sample:0/run")
    assert again.json()["already_processed"] is True
    assert len(client.get("/api/clients").json()) == 1


def test_staff_can_add_and_run_their_own_example(client):
    r = client.post("/api/examples", data={"title": "Family email, new PAN", "sender": "family@example.com",
                                           "body": "I'm Meena Iyer, need ITR. Call 98765 43210."})
    assert r.status_code == 200
    example_id = r.json()["id"]
    listed = [i for i in client.get("/api/examples").json() if i["key"] == f"custom:{example_id}"]
    assert listed and listed[0]["kind"] == "added by staff" and listed[0]["processed"] is False
    run = client.post(f"/api/examples/custom:{example_id}/run")
    assert run.status_code == 200 and run.json()["outcome"] == "created"
    client_row = client.get("/api/clients").json()[0]
    assert client_row["name"] == "Meena Iyer" and client_row["phone"] == "9876543210"
    assert client.post(f"/api/examples/custom:{example_id}/run").json()["already_processed"] is True


def test_custom_example_with_a_sample_file_is_checked_like_real_intake(client):
    from app.config import SAMPLE_ATTACHMENTS_DIR
    data = (SAMPLE_ATTACHMENTS_DIR / "sample_wrong_document_electricity_bill.png").read_bytes()
    r = client.post("/api/examples", data={"title": "Wrong document example", "sender": "bill@example.com",
                                           "body": "Here is my ID proof"},
                    files={"files": ("sample_wrong_document_electricity_bill.png", data, "image/png")})
    example_id = r.json()["id"]
    run = client.post(f"/api/examples/custom:{example_id}/run").json()
    assert run["documents"][0]["status"] == "rejected"
    assert "electricity bill" in run["documents"][0]["reason"]


def test_incomplete_custom_example_is_refused(client):
    r = client.post("/api/examples", data={"title": "x", "sender": "nobody@example.com", "body": ""})
    assert r.status_code == 400
    r = client.post("/api/examples", data={"title": "Has title", "sender": "not-an-email", "body": "hi"})
    assert r.status_code == 400


def test_unknown_example_gives_404(client):
    assert client.post("/api/examples/custom:doesnotexist/run").status_code == 404
    assert client.post("/api/examples/sample:99/run").status_code == 404
