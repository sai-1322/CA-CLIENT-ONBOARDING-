"""Create a client from a photo of their documents.

Staff upload one or more photos (PAN, Aadhaar, GST certificate, bank statement). The photos are read
with the same checks as email intake, and the app proposes client details with a recommendation:

  create          all key details read cleanly                  -> staff confirm
  check           something was blurry, unread or unclear      -> staff type in or decide
  disqualify      nothing usable, or the document is wrong     -> staff confirm the rejection
  already_exists  a client with this PAN is already on file    -> no new record is made

The app suggests; a named staff member always makes the final decision.
Nothing is created from the photo until staff press the button.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from sqlite3 import Connection

from app import validators as v
from app.config import SETTINGS, UPLOAD_DIR
from app.errors import ActionError
from app.pipeline import UPLOAD_TYPES, OTHER, analyse, attach_files, create_client
from app.workflow import ACCEPTED, get_client, log, now_iso

SIMILAR_NAME = 0.9
PRIORITY = ["pan", "aadhaar", "gst_certificate", "bank_statement", "other"]


def _safe_name(name: str) -> str:
    return Path(name).name.replace(" ", "_") or "photo"


def _find_pan_client(conn: Connection, pan: str | None):
    if not pan:
        return None
    return conn.execute("SELECT id, code, name FROM clients WHERE pan = ?", (pan,)).fetchone()


def _similar_clients(conn: Connection, name: str | None, pan: str | None) -> list[dict]:
    if not name:
        return []
    matches = []
    for row in conn.execute("SELECT id, code, name, pan FROM clients").fetchall():
        if pan and row["pan"] == pan:
            continue  # same PAN is handled as 'already exists'
        if v.name_similarity(name, row["name"]) >= SIMILAR_NAME:
            matches.append({"id": row["id"], "code": row["code"], "name": row["name"], "pan": row["pan"]})
    return matches


def _recommend(analyses: list[dict], name: str | None, pan: str | None, aadhaar: str | None,
               gstin: str | None, existing, similar: list[dict]) -> dict:
    reasons: list[str] = []
    if existing:
        return {"action": "already_exists",
                "headline": f"Already exists as {existing['code']} {existing['name']}. No new client will be created.",
                "reasons": [f"The PAN {pan} is already on file for {existing['code']}."]}

    usable = [a for a in analyses if a["status"] in ACCEPTED]
    if not usable:
        reasons = [f"{a['filename']}: {a['reason'] or 'could not be read'}" for a in analyses]
        if any(a.get("recovered") for a in analyses):
            # Blurry and unreadable is not the same as wrong: staff can read the original and type it in.
            return {"action": "check",
                    "headline": "Blurry, and the app could not read it reliably. Check the original and type the details in, or disqualify.",
                    "reasons": reasons}
        return {"action": "disqualify", "headline": "Suggest disqualify: no usable document was read.", "reasons": reasons}

    blurry = [a["filename"] for a in analyses if a.get("recovered")]
    unread = [a["filename"] for a in analyses if a["status"] == "needs_verification"]
    if blurry:
        reasons.append("Blurry photo: " + ", ".join(blurry) + ". Enhanced and read, but numbers must be checked against the original.")
    if unread:
        reasons.append("Could not read the number reliably in: " + ", ".join(unread) + ".")
    if not name:
        reasons.append("No name could be read.")
    if not (pan or aadhaar or gstin):
        reasons.append("No PAN, Aadhaar or GSTIN could be read.")
    if similar:
        names = ", ".join(f"{m['code']} {m['name']}" for m in similar)
        reasons.append(f"A client with a similar name already exists: {names}. Confirm it is a different person.")
    for a in usable:
        for warning in a.get("warnings", []):
            reasons.append(f"{a['filename']}: {warning}")

    if blurry or unread or not name or not (pan or aadhaar or gstin) or similar:
        return {"action": "check", "headline": "Suggest checking first: create only after the points below are settled, or disqualify.",
                "reasons": reasons}
    return {"action": "create", "headline": "Suggest create: the name and identifier were read cleanly.",
            "reasons": reasons or ["All key details read cleanly."]}


def read_photos(conn: Connection, files: list[tuple[str, bytes]], staff: str) -> dict:
    if not staff.strip():
        raise ActionError("Enter your name so the photo reading is recorded against you")
    if not files:
        raise ActionError("Choose at least one photo of a document")
    draft_id = uuid.uuid4().hex[:16]
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    stored: list[dict] = []
    analyses: list[dict] = []
    for index, (name, content) in enumerate(files):
        path = UPLOAD_DIR / f"{draft_id}-{index}-{_safe_name(name)}"
        path.write_bytes(content)
        analysis = analyse(path, _safe_name(name))
        analyses.append(analysis)
        stored.append({"name": _safe_name(name), "path": str(path), "doc_type": analysis["doc_type"],
                       "status": analysis["status"]})

    def first(doc_type: str | None, key: str):
        for a in analyses:
            if a["status"] not in ACCEPTED:
                continue
            if doc_type and a["doc_type"] != doc_type:
                continue
            value = a.get(key)
            if value:
                return value
        return None

    name = None
    for doc_type in PRIORITY[:-1]:
        name = first(doc_type, "name")
        if name:
            break
    if not name:  # a blurry photo may still give a name; it is shown, and staff must check it
        name = next((a["name"] for a in analyses if a.get("name")), None)
    pan = first("pan", "identifier")
    gstin = first("gst_certificate", "identifier")
    aadhaar_masked = next((a["fields"]["aadhaar"]["value"] for a in analyses
                           if a["doc_type"] == "aadhaar" and a["status"] in ACCEPTED and "aadhaar" in a["fields"]), None)
    service = "GST" if gstin else "ITR"  # an ID card does not say the service; staff can change it

    existing = _find_pan_client(conn, pan)
    similar = [] if existing else _similar_clients(conn, name, pan)
    recommendation = _recommend(analyses, name, pan, aadhaar_masked, gstin, existing, similar)

    proposal = {
        "draft_id": draft_id,
        "files": [{"name": a["filename"], "doc_type": a["doc_type"], "status": a["status"],
                   "reason": a["reason"], "blurry": bool(a.get("recovered"))} for a in analyses],
        "fields": {"name": name, "pan": pan, "aadhaar": aadhaar_masked, "gstin": gstin, "service": service,
                   "email": "", "phone": ""},
        "recommendation": recommendation,
        "existing": {"code": existing["code"], "id": existing["id"], "name": existing["name"]} if existing else None,
        "similar": similar,
    }
    conn.execute(
        "INSERT INTO photo_drafts (id, staff, proposal_json, files_json, status, created_at) VALUES (?, ?, ?, ?, 'open', ?)",
        (draft_id, staff.strip(), json.dumps(proposal), json.dumps(stored), now_iso()),
    )
    log(conn, staff.strip(), "photo_read", existing["id"] if existing else None,
        f"Photo reading {draft_id}: suggests {recommendation['action']} ({len(files)} file(s))")
    return proposal


def _load_draft(conn: Connection, draft_id: str):
    row = conn.execute("SELECT * FROM photo_drafts WHERE id = ?", (draft_id,)).fetchone()
    if row is None:
        raise ActionError("This photo reading does not exist any more. Read the photo again", 404)
    if row["status"] != "open":
        raise ActionError(f"This photo reading is already {row['status']}", 409)
    return row


def decide(conn: Connection, draft_id: str, decision: str, data: dict, staff: str,
           confirm_similar: bool = False) -> dict:
    """Staff decision on a photo reading: 'create', or 'disqualify'. Nothing else is possible."""
    if not staff.strip():
        raise ActionError("Enter your name so the decision is recorded against you")
    row = _load_draft(conn, draft_id)
    files = json.loads(row["files_json"])
    if decision == "disqualify":
        conn.execute("UPDATE photo_drafts SET status = 'disqualified' WHERE id = ?", (draft_id,))
        note = (data.get("note") or "").strip() or "no reason given"
        log(conn, staff.strip(), "photo_disqualified", None, f"Photo reading {draft_id} disqualified: {note}")
        return {"outcome": "disqualified", "client_id": None}
    if decision != "create":
        raise ActionError("Decision must be 'create' or 'disqualify'")

    pan = (data.get("pan") or "").strip().upper() or None
    existing = _find_pan_client(conn, pan) if pan else None
    if existing:
        conn.execute("UPDATE photo_drafts SET status = 'already_exists' WHERE id = ?", (draft_id,))
        log(conn, staff.strip(), "photo_duplicate_refused", existing["id"],
            f"Photo reading {draft_id}: PAN {pan} already on file for {existing['code']}. No client created.")
        return {"outcome": "already_exists", "client_id": existing["id"], "code": existing["code"]}

    name = (data.get("name") or "").strip()
    similar = _similar_clients(conn, name, pan)
    if similar and not confirm_similar:
        names = ", ".join(f"{m['code']} {m['name']}" for m in similar)
        raise ActionError(f"A client with a similar name already exists ({names}). Tick 'create anyway' only if it is a different person", 409)

    client_id = create_client(conn, {
        "name": name, "pan": pan or "", "email": data.get("email") or "",
        "phone": data.get("phone") or "", "service": data.get("service") or "ITR",
    }, staff.strip())
    log(conn, staff.strip(), "client_created_from_photo", client_id, f"Created from photo reading {draft_id}")

    for item in files:
        # Only documents the photo actually showed are attached. Unreadable or wrong files stay in the reading.
        if item["doc_type"] not in UPLOAD_TYPES or item["status"] not in ("accepted", "accepted_needs_review", "needs_verification"):
            continue
        attach_files(conn, client_id, [(item["name"], Path(item["path"]))], item["doc_type"], staff.strip())
    conn.execute("UPDATE photo_drafts SET status = 'created' WHERE id = ?", (draft_id,))
    return {"outcome": "created", "client_id": client_id, "client": get_client(conn, client_id)["code"]}
