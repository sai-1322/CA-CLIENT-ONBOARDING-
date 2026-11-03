"""Turns OCR lines into a document type and labelled fields.

Nothing here guesses. A field is only returned if a label pattern matches a line, and that
line's OCR confidence is attached to it. Missing fields come back as missing, not invented.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Field:
    value: str
    confidence: float


# Order matters: the more specific keywords are checked first.
CLASSIFY_RULES: list[tuple[str, list[str]]] = [
    ("electricity_bill", ["ELECTRICITY BILL"]),
    ("gst_certificate", ["GST REGISTRATION", "GSTIN"]),
    ("bank_statement", ["ACCOUNT STATEMENT", "ACCOUNT HOLDER", "NAME OF ACCOUNT HOLDER"]),
    ("pan", ["INCOME TAX DEPARTMENT", "PERMANENT ACCOUNT NUMBER"]),
    ("aadhaar", ["GOVERNMENT OF INDIA", "AADHAAR"]),
]

# (field name, regex with one capture group, document types it applies to)
FIELD_PATTERNS: list[tuple[str, str, tuple[str, ...]]] = [
    # Several label wordings are accepted for the same field, because real documents differ.
    ("name", r"(?i)^name:\s*(.+)$", ("pan", "aadhaar")),
    ("pan", r"(?i)\b(?:PAN(?:\s*No\.?)?|Permanent Account Number):\s*([A-Za-z0-9 ]{10,12})\s*$", ("pan",)),
    ("aadhaar", r"(?i)\bAadhaar(?:\s*No\.?)?:\s*([0-9 ]{12,16})\s*$", ("aadhaar",)),
    ("legal_name", r"(?i)^legal name:\s*(.+)$", ("gst_certificate",)),
    ("gstin", r"(?i)\bGSTIN(?:\s*No\.?)?:\s*([0-9A-Za-z]{15})\b", ("gst_certificate",)),
    ("account_holder", r"(?i)^(?:name of )?account holder:\s*(.+?)\s*(?:A/c:.*|Account No\.?:.*)?$", ("bank_statement",)),
    ("account_number", r"(?i)\b(?:A/c|Account No\.?):\s*(\S+)", ("bank_statement",)),
]


def _fuzzy_contains(text: str, phrase: str) -> bool:
    """True if the phrase appears in the text with at most a few OCR errors."""
    from difflib import SequenceMatcher
    words = text.split()
    size = len(phrase.split())
    for start in range(0, max(1, len(words) - size + 1)):
        window = " ".join(words[start:start + size + 1])
        if SequenceMatcher(None, window, phrase).ratio() >= 0.8:
            return True
    return False


def classify(lines: list[dict]) -> str:
    text = " ".join(line["text"] for line in lines).upper()
    if not text.strip():
        return "unreadable"
    for doc_type, keywords in CLASSIFY_RULES:
        if any(keyword in text for keyword in keywords):
            return doc_type
    for doc_type, keywords in CLASSIFY_RULES:  # second pass: tolerate OCR errors in the header
        if any(_fuzzy_contains(text, keyword) for keyword in keywords):
            return doc_type
    return "unknown"


def extract_fields(doc_type: str, lines: list[dict]) -> dict[str, Field]:
    fields: dict[str, Field] = {}
    for name, pattern, applies_to in FIELD_PATTERNS:
        if doc_type not in applies_to or name in fields:
            continue
        regex = re.compile(pattern)
        for line in lines:
            match = regex.search(line["text"].strip())
            if match:
                value = match.group(1).strip()
                if value:
                    fields[name] = Field(value=value, confidence=float(line["conf"]))
                    break
    return fields
