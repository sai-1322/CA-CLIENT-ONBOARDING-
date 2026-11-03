"""HTTP API and the web dashboard (served from /static)."""
from __future__ import annotations

import hashlib
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import messages as msg_gate
from app import workflow
from app import scheduler
from app.config import DOCUMENT_LABELS, INBOX_DIR, SAMPLE_ATTACHMENTS_DIR, SETTINGS, STATIC_DIR, UPLOAD_DIR
from app.db import db, init_db, reset_db
from app.emails import MAX_EML_BYTES, EmailIn, load_samples, parse_eml
from app import examples as ex
from app.errors import ActionError
from app import photo_intake
from app.pipeline import (
    MAX_UPLOAD_BYTES, add_manual_document, attach_files, create_client, process_email, process_eml,
)
from app.workflow import get_client, now_iso


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    init_db()
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    scheduler.start()  # reminder check now, then once a day
    yield
    scheduler.stop()


app = FastAPI(title="CA Client Onboarding", version="1.0.0", lifespan=_lifespan)


@app.exception_handler(ActionError)
def _action_error(_request, exc: ActionError):
    return JSONResponse(status_code=exc.status, content={"error": exc.message})


# ---------- request bodies ----------

class StaffOnly(BaseModel):
    staff: str = ""


class ProcessSample(BaseModel):
    actor: str = "intake"


class ClientUpdate(BaseModel):
    staff: str = ""
    name: str | None = None
    pan: str | None = None
    email: str | None = None
    phone: str | None = None
    service: str | None = None


class ClientCreate(BaseModel):
    staff: str = ""
    name: str = ""
    email: str = ""
    phone: str = ""
    pan: str = ""
    service: str = "ITR"


class ManualDocument(BaseModel):
    staff: str = ""
    doc_type: str = ""
    values: dict[str, str] = {}


class ReviewAction(BaseModel):
    staff: str = ""
    action: str = "resolve"
    note: str = ""


class Reject(BaseModel):
    staff: str = ""
    note: str = ""


class MessageEdit(BaseModel):
    staff: str = ""
    subject: str | None = None
    body: str | None = None
    whatsapp_body: str | None = None


class Send(BaseModel):
    staff: str = ""
    channel: str = "email"
    confirmed: bool = False   # True only when the staff member says they pressed send in their own app


class LinkRequest(BaseModel):
    staff: str = ""
    channel: str = "email"


class PhotoDecision(BaseModel):
    staff: str = ""
    decision: str = "create"        # create | disqualify
    name: str = ""
    pan: str = ""
    email: str = ""
    phone: str = ""
    service: str = "ITR"
    confirm_similar: bool = False
    note: str = ""


class Reminders(BaseModel):
    staff: str = "scheduler"
    as_of: str | None = None


# ---------- helpers ----------

def _process_sample(conn, index: int, actor: str) -> dict:
    samples = load_samples()
    if index < 0 or index >= len(samples):
        raise ActionError("No sample email with that number", 404)
    file_name, raw = samples[index]
    return process_eml(conn, raw, file_name, actor)


def _client_payload(conn, client_id: int) -> dict:
    return workflow.client_detail(conn, client_id)


# ---------- health and intake ----------

@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "ocr_engine": SETTINGS["ocr_engine"], "firm": SETTINGS["firm_name"],
            "reminder_check": scheduler.state}


@app.get("/api/sample-emails")
def sample_emails() -> list[dict]:
    with db() as conn:
        done = {r["key"] for r in conn.execute("SELECT key FROM processed_emails")}
    out = []
    for i, (file_name, raw) in enumerate(load_samples()):
        e = _parse_for_listing(raw, file_name)
        out.append({"index": i, "key": e.title, "file": file_name, "sender": e.sender, "body": e.body,
                    "attachments": e.attachments, "processed": e.key in done})
    return out


@app.post("/api/sample-emails/{index}/process")
def process_sample(index: int, payload: ProcessSample | None = None) -> dict:
    actor = (payload.actor if payload else "intake") or "intake"
    with db() as conn:
        return _process_sample(conn, index, actor)


@app.get("/api/examples")
def list_examples() -> list[dict]:
    with db() as conn:
        done = {r["key"]: r["client_id"] for r in conn.execute("SELECT key, client_id FROM processed_emails")}
    out = []
    for i, (file_name, raw) in enumerate(load_samples()):
        e = _parse_for_listing(raw, file_name)
        out.append({
            "key": f"sample:{i}", "kind": "built-in", "title": e.title, "file": file_name, "sender": e.sender,
            "body": e.body, "attachments": e.attachments, "expected": ex.BUILTIN_EXPECTED.get(e.title, ""),
            "processed": e.key in done, "client_id": done.get(e.key),
        })
    for item in ex.custom_items():
        out.append({
            "key": f"custom:{item['id']}", "kind": "added by staff", "title": item["title"], "sender": item["sender"],
            "body": item["body"], "attachments": item["attachments"], "expected": "",
            "processed": f"example:{item['id']}" in done, "client_id": done.get(f"example:{item['id']}"),
        })
    return out


@app.post("/api/examples")
async def add_example(
    title: str = Form(...),
    sender: str = Form(...),
    body: str = Form(""),
    files: list[UploadFile] = File(default=[]),
) -> dict:
    stored = []
    for upload in files:
        content = await upload.read()
        if content:
            stored.append((upload.filename or "file", content))
    return ex.add_custom(title, sender, body, stored)


@app.post("/api/examples/{key}/run")
def run_example(key: str) -> dict:
    kind, _, ident = key.partition(":")
    with db() as conn:
        if kind == "sample" and ident.isdigit():
            return _process_sample(conn, int(ident), "examples")
        if kind == "custom":
            item = ex.find_custom(ident)
            email = EmailIn(key=f"example:{item['id']}", sender=item["sender"], body=item["body"],
                            attachments=item["attachments"])
            return {"email": email.key, **process_email(conn, email, ex.custom_file_paths(item), "examples")}
    raise ActionError("Unknown example", 404)


@app.post("/api/demo/load")
def load_demo() -> dict:
    results = []
    with db() as conn:
        for index in range(len(load_samples())):
            results.append(_process_sample(conn, index, "demo-loader"))
    return {"processed": results}


@app.post("/api/intake/eml")
async def intake_eml_files(files: list[UploadFile] = File(...)) -> dict:
    """Read one or more real .eml email files (saved from Outlook, Gmail, Apple Mail, Thunderbird)."""
    results = []
    with db() as conn:
        for upload in files:
            raw = await upload.read(MAX_EML_BYTES + 1)
            name = Path(upload.filename or "email.eml").name
            if not name.lower().endswith(".eml"):
                results.append({"file": name, "outcome": "skipped", "reason": "not an .eml email file"})
                continue
            try:
                results.append(process_eml(conn, raw, name, "intake-eml"))
            except ActionError as exc:
                results.append({"file": name, "outcome": "refused", "reason": exc.message})
    return {"results": results}


@app.post("/api/intake/inbox")
def intake_inbox() -> dict:
    """Read every .eml file in the inbox folder (data/inbox). Files already read are skipped."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    with db() as conn:
        for path in sorted(INBOX_DIR.glob("*.eml")):
            try:
                results.append(process_eml(conn, path.read_bytes(), path.name, "inbox"))
            except ActionError as exc:
                results.append({"file": path.name, "outcome": "refused", "reason": exc.message})
    return {"folder": str(INBOX_DIR), "files_found": len(results), "results": results}


@app.post("/api/intake")
async def intake(
    sender: str = Form(...),
    body: str = Form(""),
    files: list[UploadFile] = File(default=[]),
) -> dict:
    sender = sender.strip()
    if "@" not in sender:
        raise ActionError("Enter the sender's email address")
    if not body.strip() and not files:
        raise ActionError("Add the email text or at least one attachment")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored: list[tuple[str, Path | None]] = []
    digest = hashlib.sha256(f"{sender}|{body}".encode("utf-8"))
    for upload in files:
        content = await upload.read()
        if not content:
            continue
        safe_name = Path(upload.filename or "attachment").name
        path = UPLOAD_DIR / f"{uuid.uuid4().hex}-{safe_name}"
        path.write_bytes(content)
        digest.update(hashlib.sha256(content).digest())
        stored.append((safe_name, path))
    key = "upload:" + digest.hexdigest()[:24]
    email = EmailIn(key=key, sender=sender, body=body.strip(), attachments=[n for n, _ in stored])
    with db() as conn:
        return process_email(conn, email, stored, "intake-form")


# ---------- clients ----------

@app.get("/api/doc-types")
def doc_types() -> list[dict]:
    return [{"key": key, "label": label} for key, label in DOCUMENT_LABELS.items()]


@app.get("/api/clients")
def clients(q: str | None = None) -> list[dict]:
    with db() as conn:
        rows = workflow.list_clients(conn)
    if q and q.strip():
        needle = q.strip().lower()
        rows = [r for r in rows if needle in " ".join(
            str(r[k] or "") for k in ("code", "name", "pan", "email", "phone", "service")).lower()]
    return rows


@app.post("/api/clients")
def add_client(payload: ClientCreate) -> dict:
    with db() as conn:
        new_id = create_client(conn, payload.model_dump(exclude={"staff"}), payload.staff)
        return _client_payload(conn, new_id)


@app.post("/api/photo-intake")
async def photo_reading(staff: str = Form(""), files: list[UploadFile] = File(...)) -> dict:
    """Read photos of documents and propose client details. Nothing is created here."""
    allowed = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".pdf"}
    received: list[tuple[str, bytes]] = []
    for upload in files:
        name = Path(upload.filename or "photo").name
        if Path(name).suffix.lower() not in allowed:
            raise ActionError(f"'{name}' is not a supported photo. Use PNG, JPG or PDF")
        content = await upload.read()
        if not content:
            continue
        if len(content) > MAX_UPLOAD_BYTES:
            raise ActionError(f"'{name}' is larger than 15 MB. Please send a smaller photo")
        received.append((name, content))
    with db() as conn:
        return photo_intake.read_photos(conn, received, staff)


@app.post("/api/photo-intake/{draft_id}/decision")
def photo_decision(draft_id: str, payload: PhotoDecision) -> dict:
    """Staff make the final call: create the client, or disqualify. 'Already exists' is never created."""
    with db() as conn:
        result = photo_intake.decide(conn, draft_id, payload.decision, payload.model_dump(exclude={"staff"}),
                                     payload.staff, payload.confirm_similar)
        if result.get("client_id"):
            return {**result, **_client_payload(conn, result["client_id"])}
        return result


@app.post("/api/clients/{client_id}/documents")
async def upload_documents(
    client_id: int,
    doc_type: str = Form(...),
    staff: str = Form(""),
    label: str = Form(""),
    files: list[UploadFile] = File(...),
) -> dict:
    if not staff.strip():
        raise ActionError("Enter your name so the upload is recorded against you")
    allowed = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".pdf"}
    stored: list[tuple[str, Path]] = []
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for upload in files:
        safe_name = Path(upload.filename or "document").name
        if Path(safe_name).suffix.lower() not in allowed:
            raise ActionError(f"'{safe_name}' is not a supported file. Use PDF, PNG, JPG or a scan image")
        content = await upload.read()
        if not content:
            continue
        if len(content) > MAX_UPLOAD_BYTES:
            raise ActionError(f"'{safe_name}' is larger than 15 MB. Please send a smaller scan")
        path = UPLOAD_DIR / f"{uuid.uuid4().hex}-{safe_name}"
        path.write_bytes(content)
        stored.append((safe_name, path))
    if not stored:
        raise ActionError("No file was received. Choose a file and try again")
    with db() as conn:
        attach_files(conn, client_id, stored, doc_type, staff.strip(), label)
        return _client_payload(conn, client_id)


@app.post("/api/clients/{client_id}/documents/manual")
def manual_document(client_id: int, payload: ManualDocument) -> dict:
    with db() as conn:
        add_manual_document(conn, client_id, payload.doc_type, payload.values, payload.staff)
        return _client_payload(conn, client_id)


@app.get("/api/clients/{client_id}")
def client_detail(client_id: int) -> dict:
    with db() as conn:
        return _client_payload(conn, client_id)


@app.patch("/api/clients/{client_id}")
def edit_client(client_id: int, payload: ClientUpdate) -> dict:
    with db() as conn:
        workflow.update_client(conn, client_id, payload.model_dump(exclude={"staff"}), payload.staff)
        return _client_payload(conn, client_id)


@app.post("/api/clients/{client_id}/onboard")
def onboard(client_id: int, payload: StaffOnly) -> dict:
    with db() as conn:
        workflow.onboard(conn, client_id, payload.staff)
        return _client_payload(conn, client_id)


# ---------- review queue ----------

@app.get("/api/review")
def review_queue() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT r.*, c.code, c.name AS client_name FROM review_items r JOIN clients c ON c.id = r.client_id "
            "WHERE r.status = 'open' ORDER BY r.id"
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/review/{item_id}/resolve")
def resolve(item_id: int, payload: ReviewAction) -> dict:
    with db() as conn:
        row = conn.execute("SELECT client_id FROM review_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise ActionError(f"Review item {item_id} does not exist", 404)
        workflow.resolve_review(conn, item_id, payload.staff, payload.action, payload.note)
        client = get_client(conn, row["client_id"])
        workflow.refresh_missing_docs_draft(conn, client, payload.staff)
        return _client_payload(conn, row["client_id"])


# ---------- messages and the approval gate ----------

@app.get("/api/messages")
def messages(status: str | None = None) -> list[dict]:
    sql = (
        "SELECT m.*, c.code, c.name AS client_name FROM messages m JOIN clients c ON c.id = m.client_id "
    )
    params: tuple = ()
    if status:
        sql += "WHERE m.status = ? "
        params = (status,)
    sql += "ORDER BY m.id DESC"
    with db() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


@app.patch("/api/messages/{message_id}")
def edit_message(message_id: int, payload: MessageEdit) -> dict:
    with db() as conn:
        msg_gate.edit(conn, message_id, payload.subject, payload.body, payload.whatsapp_body, payload.staff)
        return {"ok": True}


@app.post("/api/messages/{message_id}/approve")
def approve(message_id: int, payload: StaffOnly) -> dict:
    with db() as conn:
        msg_gate.approve(conn, message_id, payload.staff)
        return {"ok": True}


@app.post("/api/messages/{message_id}/reject")
def reject(message_id: int, payload: Reject) -> dict:
    with db() as conn:
        msg_gate.reject(conn, message_id, payload.staff, payload.note)
        return {"ok": True}


@app.post("/api/messages/{message_id}/link")
def prepare_link(message_id: int, payload: LinkRequest) -> dict:
    """Make the WhatsApp or email link for an approved draft. Nothing is sent by this call."""
    with db() as conn:
        return msg_gate.prepare_link(conn, message_id, payload.channel, payload.staff)


@app.post("/api/messages/{message_id}/send")
def confirm_send(message_id: int, payload: Send) -> dict:
    """Staff confirms they pressed send in their own app. Refused unless the draft is approved."""
    with db() as conn:
        return msg_gate.confirm_sent(conn, message_id, payload.channel, payload.staff, payload.confirmed)


@app.get("/api/outbox")
def outbox() -> list[dict]:
    with db() as conn:
        return msg_gate.outbox(conn)


@app.post("/api/reminders/run")
def run_reminders(payload: Reminders) -> dict:
    as_of = date.fromisoformat(payload.as_of) if payload.as_of else datetime.now(timezone.utc).date()
    with db() as conn:
        created = workflow.run_reminders(conn, as_of, payload.staff or "scheduler")
    return {"as_of": as_of.isoformat(), "drafts_created": created, "checked_at": now_iso()}


# ---------- helpers for listings ----------

def _parse_for_listing(raw: bytes, file_name: str) -> EmailIn:
    return parse_eml(raw, file_name)


# ---------- demo controls ----------

@app.post("/api/demo/reset")
def demo_reset() -> dict:
    reset_db()
    init_db()
    return {"ok": True}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
