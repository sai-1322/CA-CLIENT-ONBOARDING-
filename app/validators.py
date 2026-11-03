"""Identifier checks for Indian KYC documents.

Two kinds of problem are kept apart on purpose:
  * errors   - the value is not even a well-formed identifier. The document is rejected.
  * warnings - the value is well-formed but a real-world check fails (checksum, unusual
               leading digit, unknown PAN holder code). The document is accepted but a
               staff member must verify it against the original before onboarding.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
PAN_HOLDER_CODES = set("PCHFATBLJG")  # 4th character of a real PAN
GSTIN_RE = re.compile(r"^([0-9]{2})([A-Z]{5}[0-9]{4}[A-Z])[1-9A-Z]Z[0-9A-Z]$")
GST_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Verhoeff checksum tables (used by Aadhaar)
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


@dataclass
class Check:
    value: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


def normalise_name(name: str | None) -> str:
    return re.sub(r"\s+", " ", (name or "").upper()).strip()


def name_similarity(a: str | None, b: str | None) -> float:
    a, b = normalise_name(a), normalise_name(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def verhoeff_valid(number: str) -> bool:
    c = 0
    for i, digit in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(digit)]]
    return c == 0


def verhoeff_check_digit(number_without_check: str) -> str:
    """Compute the check digit to append to a number (used by tests and by data-entry helpers)."""
    c = 0
    for i, digit in enumerate(reversed(number_without_check)):
        c = _D[c][_P[(i + 1) % 8][int(digit)]]
    return str(_INV[c])


def gstin_check_char(first_14: str) -> str:
    total = 0
    for i, ch in enumerate(first_14):
        factor = 1 if i % 2 == 0 else 2
        product = factor * GST_CHARSET.index(ch)
        total += product // 36 + product % 36
    return GST_CHARSET[(36 - total % 36) % 36]


def validate_pan(raw: str | None) -> Check:
    value = re.sub(r"\s+", "", raw or "").upper()
    check = Check(value=value)
    if not PAN_RE.match(value):
        check.errors.append(f"PAN must be 5 letters, 4 digits and 1 letter (found '{value or 'nothing'}')")
        return check
    if value[3] not in PAN_HOLDER_CODES:
        check.warnings.append(f"4th character '{value[3]}' is not a standard PAN holder type; verify the card")
    return check


def validate_aadhaar(raw: str | None) -> Check:
    digits = re.sub(r"\D", "", raw or "")
    check = Check(value=digits)
    if len(digits) != 12:
        check.errors.append("Aadhaar must have 12 digits")
        return check
    if digits[0] in "01":
        check.warnings.append("Aadhaar numbers never start with 0 or 1; verify the card")
    if not verhoeff_valid(digits):
        check.warnings.append("Aadhaar checksum does not verify; possible typo or test data")
    return check


def validate_gstin(raw: str | None) -> Check:
    value = re.sub(r"\s+", "", raw or "").upper()
    check = Check(value=value)
    match = GSTIN_RE.match(value)
    if not match:
        check.errors.append(f"GSTIN must be 15 characters in GST format (found '{value or 'nothing'}')")
        return check
    if not 1 <= int(match.group(1)) <= 38:
        check.errors.append("GSTIN state code is not a valid Indian state code")
        return check
    if value[14] != gstin_check_char(value[:14]):
        check.warnings.append("GSTIN check character does not verify; possible typo or test data")
    return check


def embedded_pan_from_gstin(gstin: str) -> str:
    """Characters 3-12 of a GSTIN are the PAN of the taxpayer."""
    return gstin[2:12]


def mask_aadhaar(digits: str) -> str:
    """Only the last four digits may ever be stored or shown."""
    return "XXXX XXXX " + digits[-4:] if len(digits) == 12 else "XXXX XXXX XXXX"
