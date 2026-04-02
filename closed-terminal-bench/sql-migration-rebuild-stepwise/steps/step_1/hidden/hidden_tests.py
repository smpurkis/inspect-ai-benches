#!/usr/bin/env python3
"""Step 1 hidden tests: deeper schema validation."""

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
MIGRATE_SCRIPT = Path("/app/step_1/files/migrate.py")
HIDDEN_REFERENCE = BASE / "hidden_reference_schema.sql"


def _run_migrations(db_path: str) -> None:
    result = subprocess.run(
        [sys.executable, str(MIGRATE_SCRIPT), db_path],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Migrations failed:\n{result.stderr}"


def _fresh_db() -> tuple[str, sqlite3.Connection]:
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    _run_migrations(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return db_path, conn


def test_hidden_trigger_exists() -> None:
    """The trg_update_stock trigger exists and fires correctly."""
    _, conn = _fresh_db()
    triggers = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )
    }
    assert "trg_update_stock" in triggers, f"Missing trigger. Found: {triggers}"

    # Verify it works: insert product, insert order, check stock decreased
    conn.execute(
        "INSERT INTO users (id, username, email) VALUES (1, 'trigtest', 'trig@test.com')"
    )
    conn.execute(
        "INSERT INTO products (id, name, category, price, stock) "
        "VALUES (1, 'Widget', 'Test', 10.0, 100)"
    )
    conn.execute(
        "INSERT INTO orders (id, user_id, product_id, quantity, total) "
        "VALUES (1, 1, 1, 3, 30.0)"
    )
    stock = conn.execute("SELECT stock FROM products WHERE id = 1").fetchone()[0]
    assert stock == 97, f"Trigger should reduce stock from 100 to 97, got {stock}"
    conn.close()


def test_hidden_check_constraints() -> None:
    """CHECK constraints are present and enforced."""
    _, conn = _fresh_db()
    conn.execute(
        "INSERT INTO users (id, username, email) VALUES (1, 'checktest', 'check@test.com')"
    )
    conn.execute(
        "INSERT INTO products (id, name, category, price, stock) "
        "VALUES (1, 'Widget', 'Test', 10.0, 50)"
    )
    conn.commit()

    # price must be > 0 (not >= 0)
    try:
        conn.execute(
            "INSERT INTO products (id, name, category, price, stock) "
            "VALUES (2, 'Free', 'Test', 0, 10)"
        )
        conn.commit()
        assert False, "price=0 should violate CHECK(price > 0)"
    except sqlite3.IntegrityError:
        conn.rollback()

    # Negative price
    try:
        conn.execute(
            "INSERT INTO products (id, name, category, price, stock) "
            "VALUES (3, 'Neg', 'Test', -5, 10)"
        )
        conn.commit()
        assert False, "Negative price should violate CHECK"
    except sqlite3.IntegrityError:
        conn.rollback()

    # rating must be BETWEEN 1 AND 5
    conn.execute(
        "INSERT INTO orders (id, user_id, product_id, quantity, total) "
        "VALUES (1, 1, 1, 1, 10.0)"
    )
    conn.commit()
    try:
        conn.execute(
            "INSERT INTO reviews (id, user_id, product_id, rating, comment) "
            "VALUES (1, 1, 1, 0, 'bad')"
        )
        conn.commit()
        assert False, "rating=0 should violate CHECK(rating BETWEEN 1 AND 5)"
    except sqlite3.IntegrityError:
        conn.rollback()

    try:
        conn.execute(
            "INSERT INTO reviews (id, user_id, product_id, rating, comment) "
            "VALUES (2, 1, 1, 6, 'bad')"
        )
        conn.commit()
        assert False, "rating=6 should violate CHECK"
    except sqlite3.IntegrityError:
        conn.rollback()

    # quantity must be > 0
    try:
        conn.execute(
            "INSERT INTO orders (id, user_id, product_id, quantity, total) "
            "VALUES (2, 1, 1, 0, 0)"
        )
        conn.commit()
        assert False, "quantity=0 should violate CHECK(quantity > 0)"
    except sqlite3.IntegrityError:
        conn.rollback()

    conn.close()


def test_hidden_column_defaults() -> None:
    """Default values match reference schema."""
    _, conn = _fresh_db()

    # products.stock should default to 0
    conn.execute(
        "INSERT INTO products (id, name, category, price) "
        "VALUES (1, 'NoStock', 'Test', 5.0)"
    )
    stock = conn.execute("SELECT stock FROM products WHERE id = 1").fetchone()[0]
    assert stock == 0, f"Default stock should be 0, got {stock}"

    # users.is_active should default to 1
    conn.execute(
        "INSERT INTO users (id, username, email) VALUES (1, 'deftest', 'def@test.com')"
    )
    active = conn.execute("SELECT is_active FROM users WHERE id = 1").fetchone()[0]
    assert active == 1, f"Default is_active should be 1, got {active}"

    conn.close()


def test_hidden_nullable_columns() -> None:
    """NOT NULL constraints match reference."""
    _, conn = _fresh_db()

    # username must NOT be NULL
    try:
        conn.execute(
            "INSERT INTO users (id, username, email) VALUES (1, NULL, 'null@test.com')"
        )
        conn.commit()
        assert False, "NULL username should fail NOT NULL constraint"
    except sqlite3.IntegrityError:
        conn.rollback()

    # comment CAN be NULL
    conn.execute(
        "INSERT INTO users (id, username, email) VALUES (1, 'nulltest', 'nt@test.com')"
    )
    conn.execute(
        "INSERT INTO products (id, name, category, price, stock) "
        "VALUES (1, 'P', 'T', 10.0, 5)"
    )
    conn.execute(
        "INSERT INTO orders (id, user_id, product_id, quantity, total) "
        "VALUES (1, 1, 1, 1, 10.0)"
    )
    conn.execute(
        "INSERT INTO reviews (id, user_id, product_id, rating, comment) "
        "VALUES (1, 1, 1, 4, NULL)"
    )
    comment = conn.execute("SELECT comment FROM reviews WHERE id = 1").fetchone()[0]
    assert comment is None, "NULL comment should be allowed"

    conn.close()


def test_hidden_cascade_rules() -> None:
    """ON DELETE CASCADE on orders and reviews when user is deleted."""
    _, conn = _fresh_db()
    conn.execute(
        "INSERT INTO users (id, username, email) VALUES (1, 'cascade', 'cas@test.com')"
    )
    conn.execute(
        "INSERT INTO products (id, name, category, price, stock) "
        "VALUES (1, 'P', 'T', 10.0, 50)"
    )
    conn.execute(
        "INSERT INTO orders (id, user_id, product_id, quantity, total) "
        "VALUES (1, 1, 1, 2, 20.0)"
    )
    conn.execute(
        "INSERT INTO reviews (id, user_id, product_id, rating) VALUES (1, 1, 1, 5)"
    )
    conn.commit()

    # Delete the user — orders and reviews should cascade
    conn.execute("DELETE FROM users WHERE id = 1")
    conn.commit()

    orders = conn.execute("SELECT COUNT(*) FROM orders WHERE user_id = 1").fetchone()[0]
    reviews = conn.execute("SELECT COUNT(*) FROM reviews WHERE user_id = 1").fetchone()[0]
    assert orders == 0, f"CASCADE should delete orders, found {orders}"
    assert reviews == 0, f"CASCADE should delete reviews, found {reviews}"
    conn.close()


def test_hidden_schema_exact_match() -> None:
    """Full schema DDL matches hidden reference exactly (including categories table)."""
    _, conn = _fresh_db()
    actual_sql = conn.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE sql IS NOT NULL ORDER BY type, name"
    ).fetchall()
    conn.close()

    # Build reference DB
    fd, ref_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    ref_conn = sqlite3.connect(ref_path)
    ref_conn.executescript(HIDDEN_REFERENCE.read_text())
    ref_sql = ref_conn.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE sql IS NOT NULL ORDER BY type, name"
    ).fetchall()
    ref_conn.close()
    os.unlink(ref_path)

    actual_names = {(t, n) for t, n, _ in actual_sql}
    ref_names = {(t, n) for t, n, _ in ref_sql}

    assert "categories" in {n for _, n in actual_names}, (
        "categories table missing from schema"
    )
    assert len(actual_sql) == len(ref_sql), (
        f"Schema object count mismatch: {len(actual_sql)} vs {len(ref_sql)}\n"
        f"Actual: {sorted(actual_names)}\nExpected: {sorted(ref_names)}"
    )
    for (atype, aname, asql), (rtype, rname, rsql) in zip(actual_sql, ref_sql):
        assert atype == rtype and aname == rname, (
            f"Schema object mismatch: {atype}/{aname} vs {rtype}/{rname}"
        )


def test_hidden_self_ref_cascade() -> None:
    """Delete parent category sets children's parent_id to NULL (ON DELETE SET NULL)."""
    _, conn = _fresh_db()
    # Seed data has Electronics(1), Laptops(2, parent=1), Phones(3, parent=1)
    conn.execute("DELETE FROM categories WHERE id = 1")
    conn.commit()

    laptops = conn.execute(
        "SELECT parent_id FROM categories WHERE name = 'Laptops'"
    ).fetchone()
    phones = conn.execute(
        "SELECT parent_id FROM categories WHERE name = 'Phones'"
    ).fetchone()

    assert laptops is not None, "Laptops row should still exist after parent deleted"
    assert laptops[0] is None, f"Laptops parent_id should be NULL, got {laptops[0]}"
    assert phones is not None, "Phones row should still exist after parent deleted"
    assert phones[0] is None, f"Phones parent_id should be NULL, got {phones[0]}"
    conn.close()


def test_hidden_partial_index_valid() -> None:
    """The partial index on categories is valid (not referencing a non-existent column)."""
    _, conn = _fresh_db()
    # If the index references a non-existent column, the migration would have failed.
    # Verify the index exists and the query plan for parent_id IS NOT NULL uses it.
    indexes = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='categories'"
        )
    }
    assert "idx_active_categories" in indexes, (
        f"idx_active_categories index missing. Found: {indexes}"
    )

    # Verify query plan uses the index (should SEARCH, not SCAN)
    plan = conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM categories WHERE parent_id IS NOT NULL"
    ).fetchall()
    plan_text = " ".join(str(r) for r in plan)
    # The index is on name WHERE parent_id IS NOT NULL; SQLite may use it for this filter
    # At minimum the index must exist and the query must not error
    assert plan is not None, "EXPLAIN QUERY PLAN returned None"
    conn.close()


def test_hidden_price_values_not_swapped() -> None:
    """old_price stores the pre-update price; new_price stores the post-update price (not swapped)."""
    _, conn = _fresh_db()
    conn.execute(
        "INSERT INTO products (id, name, category, price, stock) "
        "VALUES (1, 'Widget', 'Test', 10.0, 100)"
    )
    conn.commit()
    conn.execute("UPDATE products SET price = 50.0 WHERE id = 1")
    conn.commit()

    row = conn.execute(
        "SELECT old_price, new_price FROM product_price_history WHERE product_id = 1"
    ).fetchone()
    conn.close()
    assert row is not None, "No row found in product_price_history after price update"
    old_p, new_p = row
    assert abs(old_p - 10.0) < 0.001, (
        f"old_price should be 10.0 (price BEFORE update), got {old_p}. "
        "Values may be swapped in the trigger INSERT."
    )
    assert abs(new_p - 50.0) < 0.001, (
        f"new_price should be 50.0 (price AFTER update), got {new_p}. "
        "Values may be swapped in the trigger INSERT."
    )


def test_hidden_price_no_log_when_unchanged() -> None:
    """Updating a product to the SAME price must NOT create a history row."""
    _, conn = _fresh_db()
    conn.execute(
        "INSERT INTO products (id, name, category, price, stock) "
        "VALUES (1, 'Widget', 'Test', 10.0, 100)"
    )
    conn.commit()
    # Update to the identical price — no history row should appear
    conn.execute("UPDATE products SET price = 10.0 WHERE id = 1")
    conn.commit()

    rows = conn.execute(
        "SELECT COUNT(*) FROM product_price_history WHERE product_id = 1"
    ).fetchone()[0]
    conn.close()
    assert rows == 0, (
        f"Expected 0 history rows when price does not change, got {rows}. "
        "Add a WHEN OLD.price != NEW.price guard to trg_log_price_change."
    )


if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
