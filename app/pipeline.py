"""Document intake for both emails and direct client work.

Every document, whether it arrives by email, by upload to a client, or typed in by staff, goes
through the same checks and is stored the same way. Only the source differs.

Identity rules for emails (deliberately conservative):
  1. A PAN card that passes checks and matches an existing client's PAN   -> link to that client.
  2. Same sender email as an existing client, but a different PAN         -> create a new client
                                                                             and raise 'shared email'.
  3. Same sender email, no conflicting PAN, real documents arrived       -> link, but the documents
                                                                             are HELD until staff confirm.
  4. Same sender email, only rejected documents (blurry, wrong type)     -> link. Nothing to confirm.
  5. Otherwise                                                           -> create a new client.
Nothing is merged silently. Every decision is logged.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from sqlite3 import Connection, Row

from app import validators as v
from app.config import DOCUMENT_LABELS, SERVICES, SETTINGS, UPLOAD_DIR
from app.emails import EmailIn, parse_eml
from app.errors import ActionError
from app.extraction import classify, extract_fields
from app.ocr import OCRError, read_enhanced_lines, read_lines
from app.quality import check_quality
from app.workflow import (
    ACCEPTED, add_review, client_code, get_client, log, now_iso, refresh_missing_docs_draft,
)

MIN_CONF = SETTINGS["min_field_confidence"]
IDENTITY_FIELDS = {"pan", "aadhaar", "gstin", "account_holder", "name", "legal_name"}
OTHER = "other"

# doc type -> (field that holds the identifier, validator or None)
IDENTIFIER_RULES = {
    "pan": ("pan", v.validate_pan),
    "aadhaar": ("aadhaar", v.validate_aadhaar),
    "gst_certificate": ("gstin", v.validate_gstin),
    "bank_statement": ("account_holder", None),
}
UPLOAD_TYPES = set(IDENTIFIER_RULES) | {OTHER}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mask_fields(fields: dict) -> dict:
    """Never persist full Aadhaar or full account numbers."""
    stored = {}
    for name, field in fields.items():
        value = field.value
        if name == "aadhaar":
            value = v.mask_aadhaar(re.sub(r"\D", "", value))
        elif name == "account_number":
            value = "XXXX" + re.sub(r"\D", "", value)[-4:]
        stored[name] = {"value": value, "confidence": round(field.confidence, 3)}
    return stored


def _empty_result(filename: str) -> dict:
    return {
        "filename": filename, "sha256": "", "doc_type": "unknown", "status": "rejected",
        "reason": "", "quality": None, "warnings": [], "low_fields": [], "identifier": None,
        "name": None, "fields": {},
    }


def _analyse_blurry(path: Path, filename: str, declared_type: str | None, result: dict, why: str) -> dict:
    """A blurry scan is never thrown away for being blurry. It is enhanced, read, and checked like any other.

    The outcome depends on what can actually be read:
      * the type and the identifier read cleanly  -> accepted, flagged 'read from a blurry scan; verify'
      * the type is clear but the number is not  -> needs_verification (staff type the number in)
      * nothing reliable can be read              -> needs_verification (staff check the original)
    Nothing is guessed: an unreadable number is never filled in.
    """
    result["recovered"] = True
    if declared_type == OTHER:
        result.update(doc_type=OTHER, status="accepted_needs_review",
                      reason="blurry scan stored as an other document; verify against the original")
        return result
    try:
        lines = read_enhanced_lines(path, filename)
    except OCRError as exc:
        result.update(status="needs_verification", reason=f"{why}; enhanced reading failed ({exc}). Staff: check the original")
        return result
    if not lines:
        result.update(status="needs_verification",
                      reason=f"{why}; enhancement found no readable text. Staff: check the original and type the details in")
        return result

    doc_type = classify(lines)
    result["doc_type"] = doc_type
    if doc_type == "unknown":
        result.update(status="needs_verification",
                      reason=f"{why}; the document type could not be identified reliably. Staff: check the original")
        return result
    if declared_type and doc_type != declared_type:
        result["reason"] = (f"this looks like a {DOCUMENT_LABELS[doc_type].lower()}, "
                            f"but it was uploaded as a {DOCUMENT_LABELS[declared_type].lower()}")
        return result

    fields = extract_fields(doc_type, lines)
    result["fields"] = _mask_fields(fields)
    result["name"] = next((fields[n].value for n in ("name", "legal_name", "account_holder") if n in fields), None)
    field_name, validator = IDENTIFIER_RULES.get(doc_type, (None, None))
    if field_name is None:
        result.update(status="accepted_needs_review", reason=f"{why}; read from a blurry scan; verify against the original")
        return result
    if field_name not in fields:
        result.update(status="needs_verification",
                      reason=f"identified as a {DOCUMENT_LABELS[doc_type].lower()} from a blurry scan, but the number could not be read. "
                             "Staff: type it in from the original")
        return result
    check = validator(fields[field_name].value) if validator else v.Check(value=fields[field_name].value)
    if check.errors:
        result.update(status="needs_verification",
                      reason=f"identified as a {DOCUMENT_LABELS[doc_type].lower()} from a blurry scan, but the number did not read cleanly "
                             f"({check.errors[0]}). Staff: type it in from the original")
        return result
    result.update(status="accepted_needs_review", identifier=check.value,
                  warnings=list(check.warnings) + ["read from a blurry scan; verify against the original"],
                  reason="read from a blurry scan; verify against the original")
    return result


def analyse(path: Path | None, filename: str, declared_type: str | None = None) -> dict:
    """Check one file. Never raises for a bad document; returns a rejection with a reason instead."""
    result = _empty_result(filename)
    if path is None or not path.exists():
        result["reason"] = "the file was not attached"
        return result
    result["sha256"] = sha256_file(path)
    result["declared_type"] = declared_type

    passed, score, why = check_quality(path)
    result["quality"] = score
    if not passed:
        return _analyse_blurry(path, filename, declared_type, result, why)

    if declared_type == OTHER:
        result["doc_type"] = OTHER
        result["status"] = "accepted"
        result["reason"] = "stored as an other document; not checked automatically"
        return result

    try:
        lines = read_lines(path, filename)
    except OCRError as exc:
        result["reason"] = f"could not read the file: {exc}"
        return result
    if not lines:
        result["reason"] = ("no readable text found in this file. Re-send a clearer copy, or type the details in "
                            "manually (see the README to turn on automatic reading)")
        return result

    doc_type = classify(lines)
    result["doc_type"] = doc_type
    if doc_type == "electricity_bill":
        result["reason"] = "an electricity bill is not accepted as proof for this service. Please send a PAN card or Aadhaar"
        return result
    if doc_type == "unknown":
        result["reason"] = "document type not recognised; staff will check it manually"
        return result
    if declared_type and doc_type != declared_type:
        result["reason"] = (f"this looks like a {DOCUMENT_LABELS[doc_type].lower()}, "
                            f"but it was uploaded as a {DOCUMENT_LABELS[declared_type].lower()}")
        return result

    fields = extract_fields(doc_type, lines)
    result["fields"] = _mask_fields(fields)
    result["name"] = next((fields[n].value for n in ("name", "legal_name", "account_holder") if n in fields), None)
    field_name, validator = IDENTIFIER_RULES[doc_type]
    if field_name not in fields:
        result["reason"] = f"could not find the {DOCUMENT_LABELS[doc_type].lower()} number on the document"
        return result

    check = validator(fields[field_name].value) if validator else v.Check(value=fields[field_name].value)
    if check.errors:
        result["reason"] = check.errors[0]
        return result

    result["status"] = "accepted"
    result["identifier"] = check.value
    result["warnings"] = list(check.warnings)
    result["low_fields"] = sorted(
        name for name, field in fields.items() if name in IDENTITY_FIELDS and field.confidence < MIN_CONF
    )
    if check.warnings or result["low_fields"]:
        result["status"] = "accepted_needs_review"
        result["reason"] = "; ".join(check.warnings)
    return result


def parse_body(body: str) -> dict:
    """Light, honest parsing of the email text. Phone numbers are only taken when clearly 10 digits."""
    found: dict = {"phone": None, "service": None, "name": None}
    who = re.search(r"\bI(?:'m| am)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+)", body)
    if who:
        found["name"] = who.group(1).strip().rstrip(",.")
    phone = re.search(r"\b(\d{5})\s?(\d{5})\b", body)
    if phone:
        found["phone"] = phone.group(1) + phone.group(2)
    upper = body.upper()
    if "AUDIT" in upper:
        found["service"] = "Audit"
    elif "GST" in upper:
        found["service"] = "GST"
    elif "ITR" in upper:
        found["service"] = "ITR"
    return found


# ---------- storing documents and their review items ----------

def _insert_document(conn: Connection, client_id: int, a: dict, source: str, status: str,
                     prior: str | None, reason: str) -> int:
    cur = conn.execute(
        "INSERT INTO documents (client_id, filename, sha256, doc_type, status, prior_status, reason, fields_json, "
        "quality, source_email, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (client_id, a["filename"], a["sha256"], a["doc_type"], status, prior, reason,
         json.dumps(a["fields"]), a["quality"], source, now_iso()),
    )
    return cur.lastrowid


def _raise_document_reviews(conn: Connection, client: Row, a: dict, doc_id: int) -> None:
    client_id = client["id"]
    label = DOCUMENT_LABELS.get(a["doc_type"], "Document")
    for warning in a["warnings"]:
        add_review(conn, client_id, "verify_document", f"Verify {label} ({a['filename']}): {warning}", [doc_id])
    for field_name in a["low_fields"]:
        conf = a["fields"][field_name]["confidence"]
        add_review(conn, client_id, "verify_field",
                   f"Low OCR confidence ({conf:.0%}) on {field_name} in {a['filename']}: check the original", [doc_id])
    if a.get("name") and v.name_similarity(a["name"], client["name"]) < SETTINGS["name_match_threshold"]:
        add_review(conn, client_id, "name_mismatch",
                   f"{label} ({a['filename']}) shows '{a['name']}', but the client on file is '{client['name']}'. "
                   "Check it belongs to this client.", [doc_id])
    if a["doc_type"] == "gst_certificate" and a.get("identifier"):
        embedded = v.embedded_pan_from_gstin(a["identifier"])
        if client["pan"] and client["pan"] != embedded:
            add_review(conn, client_id, "identity_conflict",
                       f"GSTIN {a['identifier']} carries PAN {embedded}, but the PAN on file is {client['pan']}.", [doc_id])
        for other in conn.execute("SELECT code, name FROM clients WHERE pan = ? AND id != ?", (embedded, client_id)).fetchall():
            add_review(conn, client_id, "identity_conflict",
                       f"GSTIN {a['identifier']} carries PAN {embedded}, which is already the PAN of "
                       f"{other['code']} {other['name']}. Confirm these are separate taxpayers.", [doc_id])


def _store_analysis(conn: Connection, client: Row, a: dict, source: str, held_mode: bool) -> tuple[dict, int | None]:
    """Store one analysed file. Returns (summary for the response, doc id if held)."""
    status, prior, reason = a["status"], None, a["reason"]
    duplicate = None
    if a["sha256"]:
        duplicate = conn.execute(
            "SELECT created_at FROM documents WHERE client_id = ? AND sha256 = ? AND sha256 != ''",
            (client["id"], a["sha256"]),
        ).fetchone()
    if duplicate:
        status, reason = "rejected", f"duplicate: this exact file was already received on {duplicate['created_at'][:10]}"
    elif held_mode and status in ACCEPTED:
        prior, status = status, "held"
        reason = "waiting for staff to confirm this belongs to the client"

    doc_id = _insert_document(conn, client["id"], a, source, status, prior, reason)
    if not duplicate and a["status"] in ACCEPTED:
        _raise_document_reviews(conn, client, a, doc_id)
    elif not duplicate and a["status"] == "needs_verification":
        add_review(conn, client["id"], "verify_document",
                   f"Check the original of {a['filename']}: {a['reason']}", [doc_id])
    summary = {"filename": a["filename"], "doc_type": a["doc_type"], "status": status, "reason": reason}
    return summary, (doc_id if status == "held" else None)


# ---------- clients ----------

def _new_client(conn: Connection, name: str, pan: str | None, email: str, phone: str | None, service: str) -> int:
    next_id = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM clients").fetchone()[0]
    conn.execute(
        "INSERT INTO clients (id, code, name, pan, email, phone, service, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (next_id, client_code(next_id), name, pan, email, phone, service, now_iso()),
    )
    return next_id


def create_client(conn: Connection, data: dict, staff: str) -> int:
    """Staff adds a client by hand. Everything optional is validated before anything is saved."""
    if not staff.strip():
        raise ActionError("Enter your name so the new client is recorded against you")
    name = (data.get("name") or "").strip()
    if len(name) < 2:
        raise ActionError("Client name is required")
    service = data.get("service") or "ITR"
    if service not in SERVICES:
        raise ActionError("Unknown service")
    email = (data.get("email") or "").strip()
    if email and "@" not in email:
        raise ActionError("Email address looks invalid")
    phone = "".join(ch for ch in (data.get("phone") or "") if ch.isdigit())
    if phone and len(phone) != 10:
        raise ActionError("Phone must have 10 digits")
    pan = None
    pan_warnings: list[str] = []
    if (data.get("pan") or "").strip():
        check = v.validate_pan(data["pan"])
        if check.errors:
            raise ActionError(check.errors[0] + ". Client not saved.")
        pan, pan_warnings = check.value, check.warnings
        clash = conn.execute("SELECT code FROM clients WHERE pan = ?", (pan,)).fetchone()
        if clash:
            raise ActionError(f"This PAN already belongs to {clash['code']}. Open that client instead", 409)
    new_id = _new_client(conn, name, pan, email, phone or None, service)
    log(conn, staff.strip(), "client_created", new_id, f"Created by hand: {name} ({service})")
    for warning in pan_warnings:
        add_review(conn, new_id, "verify_document", f"PAN entered by staff: {warning}")
    refresh_missing_docs_draft(conn, get_client(conn, new_id), staff.strip())
    return new_id


# ---------- direct work on one client ----------

def attach_files(conn: Connection, client_id: int, files: list[tuple[str, Path]], declared_type: str,
                 staff: str, label: str = "") -> dict:
    if declared_type not in UPLOAD_TYPES:
        raise ActionError("Choose what the document is: PAN, Aadhaar, GST certificate, bank statement or other")
    client = get_client(conn, client_id)
    if client["onboarded_at"]:
        raise ActionError("Onboarded clients are locked", 409)
    results = []
    for name, path in files:
        a = analyse(path, name, declared_type)
        if declared_type == OTHER:
            a["fields"]["document_label"] = {"value": label.strip() or "Other document", "confidence": 1.0}
        summary, _ = _store_analysis(conn, client, a, source=f"upload by {staff}", held_mode=False)
        results.append(summary)
        if a["doc_type"] == "pan" and a["status"] in ACCEPTED and check_pan_free_for(conn, client, a["identifier"]):
            conn.execute("UPDATE clients SET pan = ? WHERE id = ?", (a["identifier"], client_id))
            client = get_client(conn, client_id)
    log(conn, staff, "documents_uploaded", client_id, f"{len(results)} file(s) as {declared_type}")
    refresh_missing_docs_draft(conn, get_client(conn, client_id), staff)
    return {"client_id": client_id, "documents": results}


def add_manual_document(conn: Connection, client_id: int, doc_type: str, values: dict, staff: str) -> dict:
    """Staff types the details from the original document. The same validators run; nothing is guessed."""
    if not staff.strip():
        raise ActionError("Enter your name so the entry is recorded against you")
    if doc_type not in UPLOAD_TYPES:
        raise ActionError("Choose what the document is")
    client = get_client(conn, client_id)
    if client["onboarded_at"]:
        raise ActionError("Onboarded clients are locked", 409)

    fields: dict = {}
    a = _empty_result(f"typed in by {staff.strip()}")
    a["doc_type"] = doc_type
    a["declared_type"] = doc_type
    a["sha256"] = ""

    if doc_type == OTHER:
        label = (values.get("label") or "").strip()
        if len(label) < 2:
            raise ActionError("Say what the other document is (for example: Form 16)")
        a["status"] = "accepted"
        a["filename"] = f"other: {label}"
        fields["document_label"] = {"value": label, "confidence": 1.0}
        a["reason"] = "typed in by staff; not checked automatically"
    elif doc_type == "bank_statement":
        holder = (values.get("account_holder") or values.get("name") or "").strip()
        if len(holder) < 2:
            raise ActionError("Account holder name is required")
        a["name"] = holder
        a["identifier"] = holder
        a["status"] = "accepted"
        fields["account_holder"] = {"value": holder, "confidence": 1.0}
        account = re.sub(r"\D", "", values.get("account_number") or "")
        if account:
            fields["account_number"] = {"value": "XXXX" + account[-4:], "confidence": 1.0}
        a["reason"] = "typed in by staff from the statement"
    else:
        key, validator = IDENTIFIER_RULES[doc_type]
        raw = values.get(key) or values.get("name_on_document") or ""
        check = validator(raw)
        if check.errors:
            raise ActionError(check.errors[0] + ". Not saved.")
        a["identifier"] = check.value
        a["warnings"] = list(check.warnings)
        a["status"] = "accepted_needs_review" if check.warnings else "accepted"
        a["reason"] = "; ".join(check.warnings)
        if doc_type == "aadhaar":
            fields["aadhaar"] = {"value": v.mask_aadhaar(check.value), "confidence": 1.0}
        elif doc_type == "pan":
            fields["pan"] = {"value": check.value, "confidence": 1.0}
        else:
            fields["gstin"] = {"value": check.value, "confidence": 1.0}
        name = (values.get("name") or "").strip()
        if name:
            fields["name"] = {"value": name, "confidence": 1.0}
            a["name"] = name
        if doc_type == "pan" and not name:
            a["name"] = None

    a["fields"] = fields
    if doc_type in ("pan", "aadhaar", "gst_certificate"):
        duplicate = conn.execute(
            "SELECT id FROM documents WHERE client_id = ? AND doc_type = ? AND status IN ('accepted', 'accepted_needs_review') "
            "AND fields_json LIKE ?",
            (client_id, doc_type, f'%{a["identifier"]}%' if doc_type != "aadhaar" else "%XXXX XXXX " + a["identifier"][-4:] + "%"),
        ).fetchone()
        if duplicate:
            raise ActionError(f"This {DOCUMENT_LABELS[doc_type].lower()} is already on file for this client", 409)

    doc_id = _insert_document(conn, client_id, a, f"typed in by {staff.strip()}", a["status"], None, a["reason"])
    if doc_type == "pan" and check_pan_free_for(conn, client, a["identifier"]):
        conn.execute("UPDATE clients SET pan = ? WHERE id = ?", (a["identifier"], client_id))
        client = get_client(conn, client_id)
    _raise_document_reviews(conn, client, a, doc_id)
    log(conn, staff.strip(), "document_typed_in", client_id, f"{DOCUMENT_LABELS.get(doc_type, doc_type)} entered manually")
    refresh_missing_docs_draft(conn, get_client(conn, client_id), staff.strip())
    return {"client_id": client_id, "document_id": doc_id, "status": a["status"]}


def check_pan_free_for(conn: Connection, client: Row, pan: str) -> bool:
    """Set the client's PAN from a verified PAN document only if the client has none and no one else has it."""
    if client["pan"]:
        return False
    return conn.execute("SELECT 1 FROM clients WHERE pan = ? AND id != ?", (pan, client["id"])).fetchone() is None


# ---------- email intake ----------

def process_email(conn: Connection, email: EmailIn, files: list[tuple[str, Path | None]], actor: str = "intake") -> dict:
    seen = conn.execute("SELECT client_id FROM processed_emails WHERE key = ?", (email.key,)).fetchone()
    if seen:
        return {"already_processed": True, "client_id": seen["client_id"], "outcome": "already_processed", "documents": []}

    analyses = [analyse(path, name) for name, path in files]
    body = parse_body(email.body)
    accepted = [a for a in analyses if a["status"] in ACCEPTED]
    pan_on_card = next((a["identifier"] for a in accepted if a["doc_type"] == "pan"), None)

    client = None
    held = False
    outcome = "created"
    if pan_on_card:
        client = conn.execute("SELECT * FROM clients WHERE pan = ?", (pan_on_card,)).fetchone()
        if client:
            outcome = "linked_by_pan"
    if client is None:
        same_email = conn.execute(
            "SELECT * FROM clients WHERE lower(email) = lower(?) ORDER BY id LIMIT 1", (email.sender,)
        ).fetchone()
        if same_email and pan_on_card and same_email["pan"] and same_email["pan"] != pan_on_card:
            outcome = "created_shared_email"
        elif same_email:
            client = same_email
            held = bool(accepted)
            outcome = "linked_by_email"

    if client is None:
        name = (
            next((a["name"] for a in accepted if a["name"]), None)
            or body["name"]
            or next((a["name"] for a in analyses if a["name"]), None)
            or email.sender
        )
        new_id = _new_client(conn, name, pan_on_card, email.sender, body["phone"], body["service"] or "ITR")
        client = get_client(conn, new_id)
        log(conn, actor, "client_created", new_id, f"Created from {email.key}")
        if outcome == "created_shared_email":
            other = conn.execute("SELECT code FROM clients WHERE lower(email) = lower(?) AND id != ? ORDER BY id LIMIT 1",
                                 (email.sender, new_id)).fetchone()
            add_review(conn, new_id, "shared_email",
                       f"Email {email.sender} is also used by {other['code']}, but the PAN differs. Confirm these are separate clients.")
    elif not client["phone"] and body["phone"]:
        conn.execute("UPDATE clients SET phone = ? WHERE id = ?", (body["phone"], client["id"]))
        client = get_client(conn, client["id"])

    client_id = client["id"]
    held_ids: list[int] = []
    summary_docs = []
    for a in analyses:
        summary, held_id = _store_analysis(conn, client, a, source=email.key, held_mode=held)
        summary_docs.append(summary)
        if held_id:
            held_ids.append(held_id)

    if held_ids:
        names = ", ".join(a["filename"] for a in analyses if a["status"] in ACCEPTED)
        add_review(conn, client_id, "identity_confirmation",
                   f"Confirm these documents from {email.sender} belong to {client_code(client_id)} {client['name']} "
                   f"(sender email matches, PAN does not): {names}", held_ids)

    conn.execute("INSERT INTO processed_emails (key, client_id, processed_at) VALUES (?, ?, ?)",
                 (email.key, client_id, now_iso()))
    log(conn, actor, "email_processed", client_id, f"{email.key}: {outcome}, {len(analyses)} attachment(s)")
    refresh_missing_docs_draft(conn, get_client(conn, client_id), actor)
    return {"already_processed": False, "client_id": client_id, "outcome": outcome, "documents": summary_docs}


def process_eml(conn: Connection, raw: bytes, file_name: str, actor: str = "intake") -> dict:
    """Read one real .eml file, store its attachments safely, and run it through the same intake."""
    email = parse_eml(raw, file_name)
    seen = conn.execute("SELECT client_id FROM processed_emails WHERE key = ?", (email.key,)).fetchone()
    if seen:
        return {"email": email.title, "file": file_name, "already_processed": True,
                "client_id": seen["client_id"], "outcome": "already_processed", "documents": []}

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored: list[tuple[str, Path | None]] = []
    for attachment in email.contents:
        path = UPLOAD_DIR / f"{uuid.uuid4().hex}-{attachment.name}"
        path.write_bytes(attachment.content)
        stored.append((attachment.name, path))
    result = process_email(conn, email, stored, actor)
    return {"email": email.title, "file": file_name, **result}
