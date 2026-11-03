"""The approval gate. Every outbound message passes through here.

    draft -> approve (named staff member) -> open link -> staff presses send in their own app -> confirm

Links and confirmations refuse anything that is not approved. Editing an approved draft clears its approval,
so the exact text that was approved is always the text that goes out.
"""
from __future__ import annotations

from sqlite3 import Connection, Row
from urllib.parse import quote

from app.config import SETTINGS
from app.errors import ActionError
from app.workflow import get_client, log, now_iso


def get_message(conn: Connection, message_id: int) -> Row:
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if row is None:
        raise ActionError(f"Message {message_id} does not exist", 404)
    return row


def approve(conn: Connection, message_id: int, staff: str) -> None:
    if not staff.strip():
        raise ActionError("Enter your name to approve a message")
    msg = get_message(conn, message_id)
    if msg["status"] != "pending_approval":
        raise ActionError(f"Only drafts awaiting approval can be approved (this one is '{msg['status']}')", 409)
    conn.execute(
        "UPDATE messages SET status = 'approved', approved_by = ?, approved_at = ? WHERE id = ?",
        (staff.strip(), now_iso(), message_id),
    )
    log(conn, staff.strip(), "message_approved", msg["client_id"], f"{msg['kind']} draft #{message_id} approved")


def reject(conn: Connection, message_id: int, staff: str, note: str) -> None:
    if not staff.strip():
        raise ActionError("Enter your name to reject a message")
    msg = get_message(conn, message_id)
    if msg["status"] not in ("pending_approval", "approved"):
        raise ActionError(f"This message is already '{msg['status']}'", 409)
    conn.execute(
        "UPDATE messages SET status = 'rejected', note = ? WHERE id = ?",
        (note.strip() or "rejected by staff", message_id),
    )
    log(conn, staff.strip(), "message_rejected", msg["client_id"], f"{msg['kind']} draft #{message_id} rejected")


def edit(conn: Connection, message_id: int, subject: str | None, body: str | None,
         whatsapp_body: str | None, staff: str) -> None:
    if not staff.strip():
        raise ActionError("Enter your name to edit a message")
    msg = get_message(conn, message_id)
    if msg["status"] not in ("pending_approval", "approved"):
        raise ActionError(f"A '{msg['status']}' message cannot be edited", 409)
    if body is not None and not body.strip():
        raise ActionError("The message body cannot be empty")
    was_approved = msg["status"] == "approved"
    conn.execute(
        "UPDATE messages SET subject = ?, body = ?, whatsapp_body = ?, status = 'pending_approval', "
        "approved_by = NULL, approved_at = NULL WHERE id = ?",
        (
            subject if subject is not None else msg["subject"],
            body if body is not None else msg["body"],
            whatsapp_body if whatsapp_body is not None else msg["whatsapp_body"],
            message_id,
        ),
    )
    note = " (approval removed; approve again)" if was_approved else ""
    log(conn, staff.strip(), "message_edited", msg["client_id"], f"{msg['kind']} draft #{message_id} edited{note}")


def prepare_link(conn: Connection, message_id: int, channel: str, staff: str) -> dict:
    """Build a WhatsApp or email link for an APPROVED draft. The app does not send anything itself.

    The staff member opens the link, which fills in the message in WhatsApp or their email app,
    and presses send there. Then they confirm with confirm_sent().
    """
    if channel not in ("email", "whatsapp"):
        raise ActionError("Channel must be 'email' or 'whatsapp'")
    if not staff.strip():
        raise ActionError("Enter your name so the link is recorded against you")
    msg = get_message(conn, message_id)
    if msg["status"] != "approved" or not msg["approved_by"]:
        raise ActionError("Blocked: this message has not been approved by a staff member", 403)
    client = get_client(conn, msg["client_id"])
    if channel == "whatsapp":
        digits = "".join(ch for ch in (client["phone"] or "") if ch.isdigit())
        if len(digits) != 10:
            raise ActionError("No phone number on file for this client. Add one, or use email", 409)
        number = SETTINGS["default_country_code"] + digits
        url = f"https://wa.me/{number}?text={quote(msg['whatsapp_body'])}"
        recipient = "+" + number
    else:
        if not client["email"]:
            raise ActionError("No email address on file for this client. Add one, or use WhatsApp", 409)
        recipient = client["email"]
        url = f"mailto:{quote(recipient)}?subject={quote(msg['subject'])}&body={quote(msg['body'])}"
    log(conn, staff.strip(), "message_link_prepared", msg["client_id"],
        f"{msg['kind']} #{message_id}: {channel} link made. Not sent yet.")
    return {"message_id": message_id, "channel": channel, "recipient": recipient, "url": url}


def confirm_sent(conn: Connection, message_id: int, channel: str, staff: str, confirmed: bool) -> dict:
    """Record that a person pressed send in their own app. Only approved drafts can be recorded."""
    if channel not in ("email", "whatsapp"):
        raise ActionError("Channel must be 'email' or 'whatsapp'")
    msg = get_message(conn, message_id)
    if msg["status"] != "approved" or not msg["approved_by"]:
        raise ActionError("Blocked: this message has not been approved by a staff member", 403)
    if not staff.strip():
        raise ActionError("Enter your name so the send is recorded against you")
    if not confirmed:
        raise ActionError("Press send in WhatsApp or your email app first, then tick 'I have sent it'", 400)
    client = get_client(conn, msg["client_id"])
    recipient = client["email"] if channel == "email" else client["phone"]
    if not recipient:
        raise ActionError("No contact on file for this channel", 409)
    stamp = now_iso()
    conn.execute(
        "UPDATE messages SET status = 'sent', channel = ?, sent_at = ? WHERE id = ?",
        (channel, stamp, message_id),
    )
    conn.execute(
        "INSERT INTO outbox (message_id, channel, recipient, mode, created_at) VALUES (?, ?, ?, 'staff_confirmed', ?)",
        (message_id, channel, recipient, stamp),
    )
    log(conn, staff.strip(), "message_sent_confirmed", msg["client_id"],
        f"{msg['kind']} #{message_id} sent via {channel} by {staff.strip()} (confirmed by staff)")
    return {"message_id": message_id, "channel": channel, "recipient": recipient, "mode": "staff_confirmed"}


def outbox(conn: Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT o.*, m.kind, m.client_id, c.code, c.name FROM outbox o "
        "JOIN messages m ON m.id = o.message_id JOIN clients c ON c.id = m.client_id ORDER BY o.id DESC"
    ).fetchall()
    return [dict(r) for r in rows]
