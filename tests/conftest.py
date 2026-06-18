"""Pytest safety fixtures.

Tests should not read or write the project business database by default. Some
legacy test modules still execute database work at import time, so the fallback
test database must be selected before those modules are imported.
"""

import os
import tempfile
from pathlib import Path

import pytest

from src.db_connection import init_database


SESSION_TEST_DB = Path(tempfile.gettempdir()) / f"finance_dw_pytest_{os.getpid()}.db"
os.environ.setdefault("FINANCE_DW_DB_PATH", str(SESSION_TEST_DB))

init_database()


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCE_DW_DB_PATH", str(tmp_path / "finance_dw_test.db"))


def pytest_sessionfinish(session, exitstatus):
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(SESSION_TEST_DB) + suffix)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
