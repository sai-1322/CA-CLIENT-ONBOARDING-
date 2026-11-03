"""Background reminder check: runs when the app starts, then again every day (settings: reminder_check_hours).

It only drafts reminders for clients who are past the reminder period. Every draft still needs
a named staff approval, and nothing is sent. Turn off with the environment variable ONBOARDING_NO_SCHEDULER=1
(the tests do this so they stay predictable).
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from app import workflow
from app.config import SETTINGS
from app.db import db

_stop = threading.Event()
state: dict = {"enabled": False, "last_run": None, "last_drafts": 0, "last_error": None}


def run_once() -> int:
    """Run one check now. Returns how many reminder drafts were created."""
    with db() as conn:
        created = workflow.run_reminders(conn, datetime.now(timezone.utc).date(), "scheduler")
    state.update(last_run=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 last_drafts=len(created), last_error=None)
    return len(created)


def _loop(interval_seconds: float) -> None:
    while not _stop.is_set():
        try:
            run_once()
        except Exception as exc:  # keep the loop alive; the error is shown on the dashboard
            state["last_error"] = str(exc)[:200]
        _stop.wait(interval_seconds)


def start() -> threading.Thread | None:
    if os.environ.get("ONBOARDING_NO_SCHEDULER"):
        state["enabled"] = False
        return None
    hours = float(SETTINGS.get("reminder_check_hours", 24))
    state["enabled"] = True
    thread = threading.Thread(target=_loop, args=(hours * 3600,), name="reminder-check", daemon=True)
    thread.start()
    return thread


def stop() -> None:
    _stop.set()
