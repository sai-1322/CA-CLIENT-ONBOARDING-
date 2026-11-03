"""Test setup: every test run uses its own temporary database and upload folder."""
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp(prefix="onboarding-tests-")
os.environ["ONBOARDING_DATA_DIR"] = _tmp
os.environ["ONBOARDING_DB"] = str(pathlib.Path(_tmp) / "test.db")
# Sample-pack tests use the cached OCR text so they are fast and identical on every machine.
# To run every test against real Tesseract instead, set OCR_ENGINE=tesseract before running pytest.
os.environ.setdefault("OCR_ENGINE", "cache")
# No background reminder thread during tests, so results are predictable.
os.environ["ONBOARDING_NO_SCHEDULER"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import init_db, reset_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    reset_db()
    init_db()
    with TestClient(app) as c:
        yield c
    reset_db()
