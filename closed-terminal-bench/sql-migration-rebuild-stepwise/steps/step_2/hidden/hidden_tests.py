#!/usr/bin/env python3
"""Step 2 hidden tests: edge cases and full export verification."""

import hashlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ETL_SCRIPT = Path("/app/step_2/files/etl.py")
EXPORT_PATH = Path("/app/step_2/files/export.csv")
HIDDEN_REFERENCE = BASE / "hidden_reference_export.csv"
DB_PATH = "/tmp/bench.db"


def _run_etl() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    result = subprocess.run(
        [sys.executable, str(ETL_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"ETL failed:\n{result.stderr}"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_hidden_edge_case_empty_fields() -> None:
    """Empty CSV fields for nullable columns become NULL in the database."""
    _run_etl()
    conn = _get_conn()
    # Reviews with empty comments should have NULL
    null_comments = conn.execute(
        "SELECT id FROM reviews WHERE comment IS NULL ORDER BY id"
    ).fetchall()
    null_ids = [r[0] for r in null_comments]
    # Reviews 3 and 14 have empty comments (review 44 was deleted due to CDC product 12 delete)
    for expected_id in [3, 14]:
        assert expected_id in null_ids, (
            f"Review {expected_id} should have NULL comment, got non-NULL"
        )
    conn.close()


def test_hidden_cdc_idempotent() -> None:
    """Running ETL twice (fresh DB each time) produces identical export.csv."""
    _run_etl()
    export1 = EXPORT_PATH.read_text(encoding="utf-8")

    _run_etl()
    export2 = EXPORT_PATH.read_text(encoding="utf-8")

    assert export1 == export2, (
        "ETL is not idempotent: two runs produced different export.csv\n"
        f"Run 1 length: {len(export1)}, Run 2 length: {len(export2)}"
    )


def test_hidden_unicode_data_preserved() -> None:
    """Unicode content is stored and retrieved correctly."""
    _run_etl()
    conn = _get_conn()
    # User 20 has unicode name "tomás"
    row = conn.execute("SELECT username FROM users WHERE id = 20").fetchone()
    assert row is not None, "User 20 not found"
    assert row[0] == "tomás", f"Unicode username not preserved: {row[0]!r}"
    conn.close()


def test_hidden_duplicate_handling() -> None:
    """Duplicate usernames in input are handled (second occurrence skipped)."""
    _run_etl()
    conn = _get_conn()
    # Each username should appear exactly once
    dupes = conn.execute(
        "SELECT username, COUNT(*) as cnt FROM users GROUP BY username HAVING cnt > 1"
    ).fetchall()
    assert len(dupes) == 0, f"Duplicate usernames found: {dupes}"
    conn.close()


def test_hidden_computed_columns() -> None:
    """Order totals are correctly computed as price * quantity."""
    _run_etl()
    conn = _get_conn()
    # Verify a sample of orders
    rows = conn.execute("""
        SELECT o.id, o.total, p.price * o.quantity as expected_total
        FROM orders o
        JOIN products p ON p.id = o.product_id
        ORDER BY o.id
    """).fetchall()
    for oid, actual_total, expected_total in rows:
        assert abs(actual_total - expected_total) < 0.01, (
            f"Order {oid}: total={actual_total}, expected={expected_total}"
        )
    conn.close()


def test_hidden_foreign_key_integrity() -> None:
    """All foreign key references are valid."""
    _run_etl()
    conn = _get_conn()

    # All order.user_id should reference existing users
    orphan_orders = conn.execute("""
        SELECT o.id FROM orders o
        LEFT JOIN users u ON u.id = o.user_id
        WHERE u.id IS NULL
    """).fetchall()
    assert len(orphan_orders) == 0, f"Orphan orders (bad user_id): {orphan_orders}"

    # All order.product_id should reference existing products
    orphan_products = conn.execute("""
        SELECT o.id FROM orders o
        LEFT JOIN products p ON p.id = o.product_id
        WHERE p.id IS NULL
    """).fetchall()
    assert len(orphan_products) == 0, f"Orphan orders (bad product_id): {orphan_products}"

    # All review.user_id should reference existing users
    orphan_reviews = conn.execute("""
        SELECT r.id FROM reviews r
        LEFT JOIN users u ON u.id = r.user_id
        WHERE u.id IS NULL
    """).fetchall()
    assert len(orphan_reviews) == 0, f"Orphan reviews (bad user_id): {orphan_reviews}"

    conn.close()


def test_hidden_full_export_checksum() -> None:
    """SHA256 of full export matches hidden reference."""
    _run_etl()
    actual = EXPORT_PATH.read_text(encoding="utf-8")
    expected = HIDDEN_REFERENCE.read_text(encoding="utf-8")

    actual_hash = hashlib.sha256(actual.encode("utf-8")).hexdigest()
    expected_hash = hashlib.sha256(expected.encode("utf-8")).hexdigest()

    assert actual_hash == expected_hash, (
        f"Export checksum mismatch:\n  actual:   {actual_hash}\n  expected: {expected_hash}"
    )


def test_hidden_cdc_timestamp_order() -> None:
    """CDC operations applied in applied_at timestamp order, not file order.

    product_updates.csv contains two conflicting UPDATE records for product 3:
      - applied_at 2024-02-02: name='Budget Widget', price=9.99
      - applied_at 2024-02-05: name='Widget Pro',   price=29.99  (later → wins)

    The second record appears FIRST in the file; a naive file-order implementation
    would leave product 3 as 'Budget Widget'. Correct timestamp-sorted behaviour
    leaves it as 'Widget Pro' at $29.99.
    """
    _run_etl()
    conn = _get_conn()

    row = conn.execute("SELECT name, price FROM products WHERE id = 3").fetchone()
    assert row is not None, "Product 3 not found after ETL"
    assert row[0] == "Widget Pro", (
        f"Product 3 should be 'Widget Pro' (later applied_at wins), got {row[0]!r}. "
        "Sort product_updates.csv by applied_at before applying CDC."
    )
    assert abs(row[1] - 29.99) < 0.001, (
        f"Product 3 price should be 29.99, got {row[1]}"
    )

    # Order 66 (qty=1, product 3) should use the winning price $29.99
    order_row = conn.execute("SELECT total FROM orders WHERE id = 66").fetchone()
    assert order_row is not None, "Order 66 not found"
    assert abs(order_row[0] - 29.99) < 0.001, (
        f"Order 66 total should be 29.99 (Widget Pro price), got {order_row[0]}"
    )
    conn.close()


if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
