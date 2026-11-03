"""Checklist, status, review queue, drafts, reminders, onboarding and client edits.

Status rules (computed, never typed in by hand):
  new              no document has been received at all
  docs_pending     at least one required document is missing, rejected or awaiting confirmation
  ready_for_review every required document is accepted
  onboarded        a staff member has explicitly onboarded the client

Onboarding is only allowed from ready_for_review AND only when no review item is open.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from sqlite3 import Connection, Row

from app import validators as v
from app.config import DOCUMENT_LABELS, SERVICES, SETTINGS
from app.errors import ActionError

ACCEPTED = ("accepted", "accepted_needs_review")
FIRM = SETTINGS["firm_name"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def client_code(client_id: int) -> str:
    return f"C{client_id:03d}"


def log(conn: Connection, actor: str, action: str, client_id: int | None, detail: str) -> None:
    conn.execute(
        "INSERT INTO events (at, actor, action, client_id, detail) VALUES (?, ?, ?, ?, ?)",
        (now_iso(), actor, action, client_id, detail),
    )


def add_review(conn: Connection, client_id: int, kind: str, message: str, doc_ids: list[int] | None = None) -> bool:
    """Open a review item. The same item is never opened twice for the same client."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO review_items (client_id, kind, message, doc_ids_json, status, created_at) "
        "VALUES (?, ?, ?, ?, 'open', ?)",
        (client_id, kind, message, json.dumps(doc_ids or []), now_iso()),
    )
    return cur.rowcount > 0


def get_client(conn: Connection, client_id: int) -> Row:
    row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if row is None:
        raise ActionError(f"Client {client_id} does not exist", 404)
    return row


def documents_for(conn: Connection, client_id: int) -> list[Row]:
    return conn.execute("SELECT * FROM documents WHERE client_id = ? ORDER BY id", (client_id,)).fetchall()


def checklist(conn: Connection, client: Row) -> list[dict]:
    docs = documents_for(conn, client["id"])
    service = SERVICES[client["service"]]
    items = []
    for key, is_required in [(k, True) for k in service["required"]] + [(k, False) for k in service["optional"]]:
        matching = [d for d in docs if d["doc_type"] == key]
        reason = ""
        if any(d["status"] in ACCEPTED for d in matching):
            state = "received"
        elif any(d["status"] == "held" for d in matching):
            state = "awaiting_confirmation"
        elif any(d["status"] == "needs_verification" for d in matching):
            state = "needs_verification"
            reason = next(d["reason"] for d in reversed(matching) if d["status"] == "needs_verification")
        elif matching:
            state = "rejected"
            reason = matching[-1]["reason"]
        else:
            state = "missing"
        items.append({
            "key": key,
            "label": DOCUMENT_LABELS[key],
            "required": is_required,
            "state": state,
            "reason": reason,
        })
    return items


def open_items(conn: Connection, client_id: int) -> list[Row]:
    return conn.execute(
        "SELECT * FROM review_items WHERE client_id = ? AND status = 'open' ORDER BY id", (client_id,)
    ).fetchall()


def status_of(conn: Connection, client: Row, items: list[dict] | None = None) -> str:
    if client["onboarded_at"]:
        return "onboarded"
    if not documents_for(conn, client["id"]):
        return "new"
    items = items if items is not None else checklist(conn, client)
    if any(item["required"] and item["state"] != "received" for item in items):
        return "docs_pending"
    return "ready_for_review"


def onboard_blockers(conn: Connection, client: Row, items: list[dict]) -> list[str]:
    blockers = []
    for item in items:
        if item["required"] and item["state"] != "received":
            blockers.append(f"{item['label']} is {item['state'].replace('_', ' ')}")
    for row in open_items(conn, client["id"]):
        blockers.append(f"Open review item: {row['message']}")
    return blockers


def client_summary(conn: Connection, client: Row) -> dict:
    items = checklist(conn, client)
    status = status_of(conn, client, items)
    return {
        "id": client["id"],
        "code": client["code"],
        "name": client["name"],
        "pan": client["pan"],
        "email": client["email"],
        "phone": client["phone"],
        "service": client["service"],
        "status": status,
        "missing": [i["label"] for i in items if i["required"] and i["state"] != "received"],
        "open_review": len(open_items(conn, client["id"])),
        "onboarded_at": client["onboarded_at"],
    }


def list_clients(conn: Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM clients ORDER BY id").fetchall()
    return [client_summary(conn, row) for row in rows]


def _doc_label(doc: Row) -> str:
    if doc["doc_type"] == "other":
        fields = json.loads(doc["fields_json"])
        return fields.get("document_label", {}).get("value", "Other document")
    if doc["doc_type"] in DOCUMENT_LABELS:
        return DOCUMENT_LABELS[doc["doc_type"]]
    return "Unrecognised document"


def client_detail(conn: Connection, client_id: int) -> dict:
    client = get_client(conn, client_id)
    items = checklist(conn, client)
    status = status_of(conn, client, items)
    docs = [
        {
            "id": d["id"],
            "filename": d["filename"],
            "doc_type": d["doc_type"],
            "doc_label": _doc_label(d),
            "status": d["status"],
            "reason": d["reason"],
            "quality": d["quality"],
            "fields": json.loads(d["fields_json"]),
            "source_email": d["source_email"],
            "created_at": d["created_at"],
        }
        for d in documents_for(conn, client_id)
    ]
    reviews = [
        {
            "id": r["id"],
            "kind": r["kind"],
            "message": r["message"],
            "status": r["status"],
            "resolved_by": r["resolved_by"],
            "resolution": r["resolution"],
        }
        for r in conn.execute("SELECT * FROM review_items WHERE client_id = ? ORDER BY id", (client_id,))
    ]
    messages = [
        {
            "id": m["id"],
            "kind": m["kind"],
            "subject": m["subject"],
            "body": m["body"],
            "whatsapp_body": m["whatsapp_body"],
            "status": m["status"],
            "approved_by": m["approved_by"],
            "approved_at": m["approved_at"],
            "sent_at": m["sent_at"],
            "channel": m["channel"],
            "note": m["note"],
            "created_at": m["created_at"],
        }
        for m in conn.execute("SELECT * FROM messages WHERE client_id = ? ORDER BY id DESC", (client_id,))
    ]
    events = [
        {"at": e["at"], "actor": e["actor"], "action": e["action"], "detail": e["detail"]}
        for e in conn.execute("SELECT * FROM events WHERE client_id = ? ORDER BY id DESC LIMIT 50", (client_id,))
    ]
    blockers = onboard_blockers(conn, client, items) if status != "onboarded" else []
    return {
        **client_summary(conn, client),
        "status": status,
        "checklist": items,
        "documents": docs,
        "review_items": reviews,
        "messages": messages,
        "events": events,
        "can_onboard": status == "ready_for_review" and not blockers,
        "onboard_blockers": blockers,
    }


# ---------- drafts and reminders ----------

def _problem_lines(conn: Connection, client: Row) -> list[str]:
    """Every rejected document the client must hear about, with the reason.

    A rejected copy is ignored once an accepted copy of the same type exists. Duplicates are skipped.
    """
    docs = documents_for(conn, client["id"])
    accepted_types = {d["doc_type"] for d in docs if d["status"] in ACCEPTED}
    lines = []
    for d in docs:
        if d["status"] != "rejected" or d["reason"].startswith("duplicate:"):
            continue
        if d["doc_type"] in accepted_types:
            continue
        lines.append(f"- {d['filename']}: {d['reason']}.")
    return lines


def _missing_labels(items: list[dict]) -> list[str]:
    return [i["label"] for i in items if i["required"] and i["state"] in ("missing", "rejected")]


def build_missing_docs_text(client: Row, items: list[dict], problems: list[str]) -> tuple[str, str, str]:
    name = client["name"].title()
    missing = _missing_labels(items)
    bullet_list = "\n".join(f"- {label}" for label in missing)
    problem_block = ""
    if problems:
        problem_block = "\n\nWe could not accept these files:\n" + "\n".join(problems)
    subject = f"{client['service']} onboarding: documents needed"
    body = (
        f"Dear {name},\n\n"
        f"Thank you for getting in touch about your {client['service']} work. To continue, please send:\n"
        f"{bullet_list}{problem_block}\n\n"
        "Please reply to this email with clear, complete copies (flat, well lit, all corners visible).\n\n"
        f"Regards,\n{FIRM}"
    )
    whatsapp = (
        f"Hi {name}, thanks for your {client['service']} request. Please send: {', '.join(missing)}."
        + (f" We could not accept {len(problems)} file(s) we emailed you about; please re-send them." if problems else "")
        + f" Reply here with clear copies. - {FIRM}"
    )
    return f"{client['service']} onboarding: documents needed", body, whatsapp


def refresh_missing_docs_draft(conn: Connection, client: Row, actor: str) -> int | None:
    """Create (or replace) the 'documents needed' draft. Nothing is sent from here."""
    items = checklist(conn, client)
    if status_of(conn, client, items) != "docs_pending":
        return None
    if not _missing_labels(items):
        return None  # only waiting on staff confirmation; nothing to ask the client for
    conn.execute(
        "UPDATE messages SET status = 'superseded' WHERE client_id = ? AND kind = 'missing_docs' AND status = 'pending_approval'",
        (client["id"],),
    )
    subject, body, whatsapp = build_missing_docs_text(client, items, _problem_lines(conn, client))
    cur = conn.execute(
        "INSERT INTO messages (client_id, kind, subject, body, whatsapp_body, status, created_at) "
        "VALUES (?, 'missing_docs', ?, ?, ?, 'pending_approval', ?)",
        (client["id"], subject, body, whatsapp, now_iso()),
    )
    log(conn, actor, "draft_created", client["id"], f"Documents-needed draft #{cur.lastrowid} created (not sent)")
    return cur.lastrowid


def _last_contact(conn: Connection, client: Row) -> date:
    row = conn.execute(
        "SELECT MAX(sent_at) AS last FROM messages WHERE client_id = ? AND status = 'sent'", (client["id"],)
    ).fetchone()
    stamp = row["last"] or client["created_at"]
    return datetime.fromisoformat(stamp).date()


def run_reminders(conn: Connection, as_of: date, actor: str) -> list[int]:
    """Draft a reminder for every docs_pending client whose last contact is old enough.

    The 'as of' date is a parameter so the reminder rule can be shown without waiting days.
    """
    created = []
    days = SETTINGS["reminder_days"]
    for client in conn.execute("SELECT * FROM clients WHERE onboarded_at IS NULL ORDER BY id").fetchall():
        items = checklist(conn, client)
        if status_of(conn, client, items) != "docs_pending" or not _missing_labels(items):
            continue
        if (as_of - _last_contact(conn, client)).days < days:
            continue
        waiting = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE client_id = ? AND status IN ('pending_approval', 'approved')",
            (client["id"],),
        ).fetchone()[0]
        if waiting:
            continue  # one open draft at a time
        name = client["name"].title()
        missing = ", ".join(_missing_labels(items))
        subject = f"Reminder: {client['service']} documents"
        body = (
            f"Dear {name},\n\nJust a friendly reminder: we are still waiting for {missing} "
            f"for your {client['service']} onboarding. Please reply when you can.\n\nRegards,\n{FIRM}"
        )
        whatsapp = f"Hi {name}, reminder: we are still waiting for {missing} for your {client['service']} onboarding. - {FIRM}"
        cur = conn.execute(
            "INSERT INTO messages (client_id, kind, subject, body, whatsapp_body, status, created_at) "
            "VALUES (?, 'reminder', ?, ?, ?, 'pending_approval', ?)",
            (client["id"], subject, body, whatsapp, now_iso()),
        )
        log(conn, actor, "reminder_drafted", client["id"], f"Reminder draft #{cur.lastrowid} for {as_of.isoformat()} (not sent)")
        created.append(cur.lastrowid)
    return created


# ---------- review queue ----------

def resolve_review(conn: Connection, item_id: int, staff: str, action: str, note: str) -> None:
    if not staff.strip():
        raise ActionError("Enter your name so the decision is recorded against you")
    item = conn.execute("SELECT * FROM review_items WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        raise ActionError(f"Review item {item_id} does not exist", 404)
    if item["status"] != "open":
        raise ActionError("This review item is already resolved", 409)
    doc_ids = json.loads(item["doc_ids_json"])

    if item["kind"] == "identity_confirmation":
        if action not in ("confirm", "reject"):
            raise ActionError("Choose 'confirm' (documents belong to this client) or 'reject'")
        for doc_id in doc_ids:
            if action == "confirm":
                conn.execute(
                    "UPDATE documents SET status = COALESCE(prior_status, 'accepted'), prior_status = NULL, reason = '' "
                    "WHERE id = ? AND status = 'held'", (doc_id,),
                )
            else:
                conn.execute(
                    "UPDATE documents SET status = 'rejected', prior_status = NULL, reason = ? WHERE id = ? AND status = 'held'",
                    ("not confirmed as belonging to this client", doc_id),
                )
        if action == "confirm":
            held_pan = conn.execute(
                "SELECT fields_json FROM documents WHERE id IN (%s) AND doc_type = 'pan' AND status IN ('accepted', 'accepted_needs_review')"
                % ",".join("?" * len(doc_ids)), doc_ids,
            ).fetchall() if doc_ids else []
            client = get_client(conn, item["client_id"])
            for row in held_pan:
                pan = json.loads(row["fields_json"]).get("pan", {}).get("value")
                if pan and not client["pan"]:
                    clash = conn.execute("SELECT id, code FROM clients WHERE pan = ? AND id != ?", (pan, client["id"])).fetchone()
                    if clash is None:
                        conn.execute("UPDATE clients SET pan = ? WHERE id = ?", (pan, client["id"]))
        else:
            # Anything raised only because of a rejected document is closed with it.
            for other in open_items(conn, item["client_id"]):
                other_docs = json.loads(other["doc_ids_json"])
                if other["id"] != item_id and other_docs and set(other_docs) & set(doc_ids):
                    conn.execute(
                        "UPDATE review_items SET status = 'resolved', resolved_by = ?, resolution = ? WHERE id = ?",
                        (staff, "closed: source document rejected", other["id"]),
                    )
        resolution = f"{action}: {note}".strip(": ")
    else:
        if action != "resolve":
            raise ActionError("Use 'resolve' after checking the original document")
        if len(note.strip()) < 3:
            raise ActionError("Write a short note saying what you checked (for the audit log)")
        resolution = note.strip()

    conn.execute(
        "UPDATE review_items SET status = 'resolved', resolved_by = ?, resolution = ? WHERE id = ?",
        (staff, resolution, item_id),
    )
    log(conn, staff, f"review_{action}", item["client_id"], f"{item['kind']}: {resolution}")


# ---------- onboarding and edits ----------

def onboard(conn: Connection, client_id: int, staff: str) -> None:
    if not staff.strip():
        raise ActionError("Enter the name of the staff member approving onboarding")
    client = get_client(conn, client_id)
    items = checklist(conn, client)
    status = status_of(conn, client, items)
    if status == "onboarded":
        raise ActionError("Client is already onboarded", 409)
    blockers = onboard_blockers(conn, client, items)
    if status != "ready_for_review" or blockers:
        raise ActionError("Cannot onboard yet: " + "; ".join(blockers), 409)
    conn.execute("UPDATE clients SET onboarded_at = ?, onboarded_by = ? WHERE id = ?", (now_iso(), staff, client_id))
    log(conn, staff, "onboarded", client_id, "Client onboarded by staff after review")


def update_client(conn: Connection, client_id: int, changes: dict, staff: str) -> None:
    if not staff.strip():
        raise ActionError("Enter your name so the change is recorded against you")
    client = get_client(conn, client_id)
    if client["onboarded_at"]:
        raise ActionError("Onboarded clients are locked. Reopen the client before editing", 409)
    updates: dict = {}
    if "name" in changes and changes["name"] is not None:
        if not changes["name"].strip():
            raise ActionError("Name cannot be empty")
        updates["name"] = changes["name"].strip()
    if "phone" in changes and changes["phone"] is not None:
        digits = "".join(ch for ch in changes["phone"] if ch.isdigit())
        if changes["phone"].strip() and len(digits) != 10:
            raise ActionError("Phone must have 10 digits")
        updates["phone"] = digits or None
    if "email" in changes and changes["email"] is not None:
        if "@" not in changes["email"]:
            raise ActionError("Email address looks invalid")
        updates["email"] = changes["email"].strip()
    if "service" in changes and changes["service"] is not None:
        if changes["service"] not in SERVICES:
            raise ActionError("Unknown service")
        updates["service"] = changes["service"]
    if "pan" in changes and changes["pan"] is not None:
        check = v.validate_pan(changes["pan"])
        if check.errors:
            raise ActionError(check.errors[0] + ". Not saved.")
        clash = conn.execute("SELECT id, code FROM clients WHERE pan = ? AND id != ?", (check.value, client_id)).fetchone()
        if clash:
            raise ActionError(f"This PAN already belongs to {clash['code']}. Possible duplicate; resolve it first", 409)
        updates["pan"] = check.value
        for message in check.warnings:
            add_review(conn, client_id, "verify_document", f"PAN entered by staff: {message}")
    if updates:
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE clients SET {assignments} WHERE id = ?", (*updates.values(), client_id))
        log(conn, staff, "client_edited", client_id, "Edited fields: " + ", ".join(updates))
