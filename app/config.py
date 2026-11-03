"""Paths and settings. Everything configurable lives in config/*.json or environment variables."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
SAMPLE_DIR = ROOT / "sample_data"
SAMPLE_ATTACHMENTS_DIR = SAMPLE_DIR / "attachments"
EMAIL_SAMPLES_DIR = SAMPLE_DIR / "emails"  # real .eml files: the built-in examples
OCR_CACHE_PATH = SAMPLE_DIR / "ocr_cache.json"
STATIC_DIR = ROOT / "static"

DATA_DIR = Path(os.environ.get("ONBOARDING_DATA_DIR", ROOT / "data"))
DB_PATH = Path(os.environ.get("ONBOARDING_DB", DATA_DIR / "onboarding.db"))
UPLOAD_DIR = DATA_DIR / "uploads"
INBOX_DIR = DATA_DIR / "inbox"  # drop .eml files here, then press "Read inbox" on the Intake page

SETTINGS: dict = json.loads((CONFIG_DIR / "settings.json").read_text(encoding="utf-8"))
if os.environ.get("OCR_ENGINE"):
    SETTINGS["ocr_engine"] = os.environ["OCR_ENGINE"]

CHECKLISTS: dict = json.loads((CONFIG_DIR / "checklists.json").read_text(encoding="utf-8"))
DOCUMENT_LABELS: dict[str, str] = CHECKLISTS["documents"]
SERVICES: dict[str, dict] = CHECKLISTS["services"]
