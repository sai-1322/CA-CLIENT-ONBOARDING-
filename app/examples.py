"""Test examples: the five sample cases (built in) plus any examples staff add themselves.

Built-in examples are real .eml files in sample_data/emails and carry the expected result, so a
reviewer can check each one. Custom examples are stored under data/examples.json with their files.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from app.config import DATA_DIR
from app.errors import ActionError

EXAMPLES_FILE = DATA_DIR / "examples.json"
EXAMPLES_DIR = DATA_DIR / "examples"

BUILTIN_EXPECTED = {
    "Email 1": "New ITR client. PAN and Aadhaar received (with checksum warnings to verify). Bank statement missing, so status is Docs pending.",
    "Email 2": "New GST client. GST certificate and bank statement received. GSTIN carries Rohan's PAN, so an identity conflict is raised.",
    "Email 3": "New Audit client. PAN ABCDE12345 is invalid, so it is rejected and the client is asked for a correct copy.",
    "Email 4 (duplicate)": "Same sender as Email 1. The blurry scan is enhanced and read, not rejected. Its PAN number is not trusted, so it is held for staff to check. No second record is created.",
    "Email 5 (wrong doc)": "Same sender as Email 1. Electricity bill rejected as proof, and the client is told why.",
    "Email 6 (new layouts)": "New client Priya Nair. Four documents in layouts the pack never used (PAN No., Permanent Account Number, Aadhaar No., GSTIN No., Name of account holder) are all read. The bank holder name differs from the client name, so it is flagged for a name check.",
}


def _load_custom() -> list[dict]:
    if not EXAMPLES_FILE.exists():
        return []
    try:
        return json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_custom(items: list[dict]) -> None:
    EXAMPLES_FILE.parent.mkdir(parents=True, exist_ok=True)
    EXAMPLES_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def add_custom(title: str, sender: str, body: str, files: list[tuple[str, bytes]]) -> dict:
    title = title.strip()
    if len(title) < 2:
        raise ActionError("Give the example a short title")
    if "@" not in sender:
        raise ActionError("Enter the sender's email address")
    if not body.strip() and not files:
        raise ActionError("Add the email text or at least one file")
    example_id = uuid.uuid4().hex[:10]
    folder = EXAMPLES_DIR / example_id
    folder.mkdir(parents=True, exist_ok=True)
    names = []
    for name, content in files:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name) or "file"
        (folder / safe).write_bytes(content)
        names.append(safe)
    item = {"id": example_id, "title": title, "sender": sender.strip(), "body": body.strip(), "attachments": names}
    items = _load_custom()
    items.append(item)
    _save_custom(items)
    return item


def custom_items() -> list[dict]:
    return _load_custom()


def find_custom(example_id: str) -> dict:
    item = next((i for i in _load_custom() if i["id"] == example_id), None)
    if item is None:
        raise ActionError("That example does not exist", 404)
    return item


def custom_file_paths(item: dict) -> list[tuple[str, Path | None]]:
    folder = EXAMPLES_DIR / item["id"]
    return [(name, folder / name if (folder / name).exists() else None) for name in item["attachments"]]
