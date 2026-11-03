"""Reads real email files (.eml) with Python's standard `email` library.

An .eml file is what a mail program saves: headers (From, Subject, Message-ID), a text body, and
attachments encoded inside the file. Nothing here assumes a fixed format. Whatever sender, subject
and attachments the file carries are read as they are.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path

from app.config import EMAIL_SAMPLES_DIR
from app.errors import ActionError

MAX_EML_BYTES = 5 * 1024 * 1024


@dataclass
class Attachment:
    name: str
    content: bytes


@dataclass
class EmailIn:
    key: str                      # Message-ID of the email (or a hash of the file). Processed once, ever.
    sender: str
    body: str
    attachments: list[str] = field(default_factory=list)   # file names, for the record
    title: str = ""               # the part of the subject before "|", shown in the examples list
    contents: list[Attachment] = field(default_factory=list)


def parse_eml(raw: bytes, file_name: str = "email.eml") -> EmailIn:
    """Read one .eml file. Raises ActionError with a plain reason if it cannot be used."""
    if len(raw) > MAX_EML_BYTES:
        raise ActionError(f"'{file_name}' is larger than 5 MB. Send the documents in a smaller email")
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
    except Exception as exc:  # a malformed file must never crash the app
        raise ActionError(f"'{file_name}' is not a readable email file ({exc})") from exc

    _, sender = parseaddr(str(message.get("From", "") or ""))
    if "@" not in sender:
        raise ActionError(f"'{file_name}' has no valid From address, so it cannot be matched to a client")

    subject = str(message.get("Subject", "") or "").strip()
    message_id = str(message.get("Message-ID", "") or "").strip().strip("<>")
    key = message_id or "file:" + hashlib.sha256(raw).hexdigest()[:24]

    text_part = message.get_body(preferencelist=("plain",))
    body = text_part.get_content().strip() if text_part is not None else ""

    contents: list[Attachment] = []
    for part in message.iter_attachments():
        name = Path(part.get_filename() or "attachment").name
        payload = part.get_payload(decode=True) or b""
        if payload:
            contents.append(Attachment(name=name, content=payload))

    return EmailIn(
        key=key,
        sender=sender,
        body=body,
        attachments=[a.name for a in contents],
        title=(subject.split("|")[0].strip() or file_name),
        contents=contents,
    )


def load_samples() -> list[tuple[str, bytes]]:
    """The built-in example emails, as (file name, raw bytes), in order."""
    return [(path.name, path.read_bytes()) for path in sorted(EMAIL_SAMPLES_DIR.glob("*.eml"))]
