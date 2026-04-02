#!/usr/bin/env python3
"""Step 2 visible tests: verify ETL pipeline produces correct output."""

import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
ETL_SCRIPT = BASE / "etl.py"
REFERENCE_EXPORT = BASE / "reference_export_public.csv"
EXPORT_PATH = BASE / "export.csv"
DB_PATH = "/tmp/bench.db"

EXPECTED_COUNTS = {
    "users": 20,
    "products": 28,
    "orders": 93,
    "reviews": 45,
}


def _run_etl() -> None:
    """Run the ETL script."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    result = subprocess.run(
        [sys.executable, str(ETL_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"ETL failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_etl_runs_without_error() -> None:
    """etl.py completes successfully."""
    _run_etl()
    assert os.path.exists(DB_PATH), "Database not created"
    assert EXPORT_PATH.exists(), "export.csv not created"


def test_row_counts_match() -> None:
    """Each table has the expected row count."""
    _run_etl()
    conn = _get_conn()
    for table, expected in EXPECTED_COUNTS.items():
        actual = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert actual == expected, f"{table}: expected {expected} rows, got {actual}"
    conn.close()


def test_sample_rows_correct() -> None:
    """Specific known rows have correct values."""
    _run_etl()
    conn = _get_conn()

    # Check user 1
    row = conn.execute("SELECT username, email FROM users WHERE id = 1").fetchone()
    assert row == ("alice", "alice@example.com"), f"User 1 mismatch: {row}"

    # Check order 1: user 1, product 1 (Wireless Mouse $29.99), qty 2 → total 59.98
    row = conn.execute(
        "SELECT user_id, product_id, quantity, total FROM orders WHERE id = 1"
    ).fetchone()
    assert row == (1, 1, 2, 59.98), f"Order 1 mismatch: {row}"

    # Check order 50: user 11, product 23 (Bookshelf $149.99), qty 1 → total 149.99
    row = conn.execute(
        "SELECT user_id, product_id, quantity, total FROM orders WHERE id = 50"
    ).fetchone()
    assert row == (11, 23, 1, 149.99), f"Order 50 mismatch: {row}"

    conn.close()


def test_cdc_updates_applied() -> None:
    """CDC UPDATE operations are reflected: product 3 has updated price and name."""
    _run_etl()
    conn = _get_conn()

    # Product 3 was HDMI Cable ($12.99) → updated to Widget Pro ($29.99) by CDC
    row = conn.execute("SELECT name, price FROM products WHERE id = 3").fetchone()
    assert row is not None, "Product 3 not found"
    assert row[0] == "Widget Pro", f"Product 3 name should be 'Widget Pro', got: {row[0]!r}"
    assert abs(row[1] - 29.99) < 0.001, f"Product 3 price should be 29.99, got: {row[1]}"

    # Orders for product 3 should use the new price (29.99); order 66 has qty 1 → total 29.99
    row = conn.execute("SELECT total FROM orders WHERE id = 66").fetchone()
    assert row is not None, "Order 66 not found"
    assert abs(row[0] - 29.99) < 0.001, f"Order 66 total should be 29.99 (updated price), got: {row[0]}"

    conn.close()


def test_cdc_deletes_cascade() -> None:
    """CDC DELETE removes products 12 and 25 and their associated orders."""
    _run_etl()
    conn = _get_conn()

    # Products 12 and 25 should not exist
    p12 = conn.execute("SELECT id FROM products WHERE id = 12").fetchone()
    assert p12 is None, "Product 12 should have been deleted by CDC"

    p25 = conn.execute("SELECT id FROM products WHERE id = 25").fetchone()
    assert p25 is None, "Product 25 should have been deleted by CDC"

    # Orders referencing product 12 (orders 25, 52, 79) should be gone
    for oid in [25, 52, 79]:
        row = conn.execute(f"SELECT id FROM orders WHERE id = {oid}").fetchone()
        assert row is None, f"Order {oid} (product 12) should have been removed by CDC delete"

    # Orders referencing product 25 (orders 5, 33, 60, 87) should be gone
    for oid in [5, 33, 60, 87]:
        row = conn.execute(f"SELECT id FROM orders WHERE id = {oid}").fetchone()
        assert row is None, f"Order {oid} (product 25) should have been removed by CDC delete"

    conn.close()


def test_export_csv_matches_reference() -> None:
    """Exported CSV matches the public reference file."""
    _run_etl()
    actual = EXPORT_PATH.read_text(encoding="utf-8")
    expected = REFERENCE_EXPORT.read_text(encoding="utf-8")
    assert actual == expected, (
        "export.csv does not match reference_export_public.csv\n"
        f"First difference at char {next((i for i, (a, e) in enumerate(zip(actual, expected)) if a != e), 'length mismatch')}"
    )


if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
