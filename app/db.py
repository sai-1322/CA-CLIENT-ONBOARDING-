"""SQLite storage. Standard library only, so there is nothing else to install or run."""
from __future__ import annotations

import shutil
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from app.config import DB_PATH, UPLOAD_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    pan           TEXT,
    email         TEXT NOT NULL,
    phone         TEXT,
    service       TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    onboarded_at  TEXT,
    onboarded_by  TEXT
);
CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id     INTEGER NOT NULL REFERENCES clients(id),
    filename      TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    doc_type      TEXT NOT NULL,
    status        TEXT NOT NULL,       -- accepted | accepted_needs_review | rejected | held
    prior_status  TEXT,                -- status to restore if a held document is confirmed
    reason        TEXT,
    fields_json   TEXT NOT NULL,       -- masked: Aadhaar is never stored in full
    quality       REAL,
    source_email  TEXT,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id     INTEGER NOT NULL REFERENCES clients(id),
    kind          TEXT NOT NULL,       -- identity_confirmation | identity_conflict | verify_document | verify_field | name_mismatch | shared_email
    message       TEXT NOT NULL,
    doc_ids_json  TEXT NOT NULL DEFAULT '[]',
    status        TEXT NOT NULL,       -- open | resolved
    resolved_by   TEXT,
    resolution    TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE (client_id, kind, message)
);
CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id     INTEGER NOT NULL REFERENCES clients(id),
    kind          TEXT NOT NULL,       -- missing_docs | reminder
    subject       TEXT NOT NULL,
    body          TEXT NOT NULL,
    whatsapp_body TEXT NOT NULL,
    status        TEXT NOT NULL,       -- pending_approval | approved | sent | rejected | superseded
    approved_by   TEXT,
    approved_at   TEXT,
    sent_at       TEXT,
    channel       TEXT,
    note          TEXT,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id    INTEGER NOT NULL REFERENCES messages(id),
    channel       TEXT NOT NULL,
    recipient     TEXT NOT NULL,
    mode          TEXT NOT NULL,       -- staff_confirmed (a person pressed send in their own app)
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    at            TEXT NOT NULL,
    actor         TEXT NOT NULL,
    action        TEXT NOT NULL,
    client_id     INTEGER,
    detail        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS photo_drafts (
    id            TEXT PRIMARY KEY,    -- one reading of uploaded photos, until staff decide
    staff         TEXT NOT NULL,
    proposal_json TEXT NOT NULL,
    files_json    TEXT NOT NULL,
    status        TEXT NOT NULL,       -- open | created | disqualified | already_exists
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS processed_emails (
    key           TEXT PRIMARY KEY,    -- idempotency key: the same email is never processed twice
    client_id     INTEGER,
    processed_at  TEXT NOT NULL
);
"""

TABLES = ["outbox", "messages", "review_items", "documents", "events", "processed_emails", "photo_drafts", "clients"]


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)  # idempotent: every statement is CREATE ... IF NOT EXISTS
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(SCHEMA)


def reset_db() -> None:
    with db() as conn:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM sqlite_sequence")
    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)
