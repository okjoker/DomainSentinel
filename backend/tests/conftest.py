"""Test configuration.

Environment is set BEFORE importing the app so the cached Settings pick up the
fake Cloudflare client, a throwaway SQLite db and blob dir, and a disabled
scheduler/autostart (the scan lifecycle is driven explicitly via the cron tick).
"""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="ds-test-")
os.environ["CF_FAKE"] = "true"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["AUTOSTART_SCANS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}/test.db"
os.environ["BLOB_LOCAL_DIR"] = f"{_TMP}/blobs"
os.environ["STATIC_DIR"] = "/nonexistent-spa"
os.environ["CRON_SECRET"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
