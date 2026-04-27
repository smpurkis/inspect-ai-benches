#!/usr/bin/env python3
"""Visible test: verify migrations execute successfully."""

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
MIGRATE_SCRIPT = BASE / "migrate.py"


def _run_migrations(db_path: str) -> None:
    result = subprocess.run(
        [sys.executable, str(MIGRATE_SCRIPT), db_path],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Migrations failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_migrations_apply_cleanly() -> None:
    """All migration files execute without errors on a fresh database."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    _run_migrations(db_path)
    conn = sqlite3.connect(db_path)
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        )
    }
    conn.close()
    os.unlink(db_path)
    assert len(tables) >= 6, (
        f"Expected at least 6 tables, got {len(tables)}: {tables}"
    )


if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
