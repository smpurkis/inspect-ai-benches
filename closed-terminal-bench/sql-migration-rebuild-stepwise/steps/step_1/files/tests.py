#!/usr/bin/env python3
"""Step 1 visible tests: verify fixed migrations produce the correct schema."""

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
MIGRATE_SCRIPT = BASE / "migrate.py"
REFERENCE_SCHEMA = BASE / "reference_schema.sql"

EXPECTED_TABLES = {"users", "products", "orders", "reviews", "categories", "product_price_history"}

EXPECTED_COLUMNS = {
    "users": [
        ("id", "INTEGER"),
        ("username", "TEXT"),
        ("email", "TEXT"),
        ("created_at", "TEXT"),
        ("is_active", "INTEGER"),
    ],
    "products": [
        ("id", "INTEGER"),
        ("name", "TEXT"),
        ("category", "TEXT"),
        ("price", "REAL"),
        ("stock", "INTEGER"),
        ("created_at", "TEXT"),
    ],
    "orders": [
        ("id", "INTEGER"),
        ("user_id", "INTEGER"),
        ("product_id", "INTEGER"),
        ("quantity", "INTEGER"),
        ("total", "REAL"),
        ("ordered_at", "TEXT"),
    ],
    "reviews": [
        ("id", "INTEGER"),
        ("user_id", "INTEGER"),
        ("product_id", "INTEGER"),
        ("rating", "INTEGER"),
        ("comment", "TEXT"),
        ("reviewed_at", "TEXT"),
    ],
}

EXPECTED_INDEXES = {
    "idx_orders_user_id",
    "idx_orders_product_id",
    "idx_reviews_product_id",
    "idx_products_category",
}


def _run_migrations(db_path: str) -> None:
    result = subprocess.run(
        [sys.executable, str(MIGRATE_SCRIPT), db_path],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Migrations failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"


def _fresh_db() -> tuple[str, sqlite3.Connection]:
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    _run_migrations(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return db_path, conn


def test_migrations_apply_cleanly() -> None:
    """All migrations run without error on a fresh database."""
    db_path, conn = _fresh_db()
    conn.close()
    os.unlink(db_path)


def test_schema_tables_exist() -> None:
    """All expected tables are present."""
    _, conn = _fresh_db()
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    conn.close()
    assert EXPECTED_TABLES.issubset(tables), f"Missing tables: {EXPECTED_TABLES - tables}"


def test_schema_columns_match() -> None:
    """Column names and types match reference for each table."""
    _, conn = _fresh_db()
    for table, expected_cols in EXPECTED_COLUMNS.items():
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        actual = [(row[1], row[2]) for row in info]
        for name, typ in expected_cols:
            matches = [(n, t) for n, t in actual if n == name]
            assert matches, f"Column {name} missing from {table}"
            assert matches[0][1] == typ, (
                f"Column {table}.{name}: expected type {typ}, got {matches[0][1]}"
            )
    conn.close()


def test_indexes_exist() -> None:
    """All required indexes are created."""
    _, conn = _fresh_db()
    indexes = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        )
    }
    conn.close()
    assert EXPECTED_INDEXES.issubset(indexes), f"Missing indexes: {EXPECTED_INDEXES - indexes}"


def test_constraints_enforced() -> None:
    """Foreign key and unique constraints are present and enforced."""
    _, conn = _fresh_db()
    # Insert a valid user
    conn.execute(
        "INSERT INTO users (id, username, email, created_at, is_active) "
        "VALUES (1, 'testuser', 'test@test.com', '2024-01-01 00:00:00', 1)"
    )
    conn.commit()

    # Duplicate username should fail
    try:
        conn.execute(
            "INSERT INTO users (id, username, email, created_at, is_active) "
            "VALUES (2, 'testuser', 'other@test.com', '2024-01-01 00:00:00', 1)"
        )
        conn.commit()
        assert False, "Duplicate username should have raised an error"
    except sqlite3.IntegrityError:
        conn.rollback()

    # Duplicate email should fail
    try:
        conn.execute(
            "INSERT INTO users (id, username, email, created_at, is_active) "
            "VALUES (2, 'otheruser', 'test@test.com', '2024-01-01 00:00:00', 1)"
        )
        conn.commit()
        assert False, "Duplicate email should have raised an error"
    except sqlite3.IntegrityError:
        conn.rollback()

    conn.close()


def test_migrations_idempotent_fresh() -> None:
    """Applying migrations on two fresh DBs produces identical schemas."""
    _, conn1 = _fresh_db()
    _, conn2 = _fresh_db()

    schema1 = conn1.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
    ).fetchall()
    schema2 = conn2.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
    ).fetchall()

    conn1.close()
    conn2.close()
    assert schema1 == schema2, "Schemas differ between two fresh migration runs"


def test_categories_table_exists() -> None:
    """categories table exists with correct columns."""
    _, conn = _fresh_db()
    info = conn.execute("PRAGMA table_info(categories)").fetchall()
    conn.close()
    col_names = [row[1] for row in info]
    assert "id" in col_names, "categories.id missing"
    assert "name" in col_names, "categories.name missing"
    assert "parent_id" in col_names, "categories.parent_id missing"
    assert "created_at" in col_names, "categories.created_at missing"


def test_self_referential_fk_works() -> None:
    """Can insert parent then child with parent_id reference; deleting parent sets child's parent_id to NULL."""
    _, conn = _fresh_db()
    # Seed data already inserted categories 1, 2, 3; verify child rows reference parent
    parent_id_laptops = conn.execute(
        "SELECT parent_id FROM categories WHERE name = 'Laptops'"
    ).fetchone()
    assert parent_id_laptops is not None, "Laptops category not found"
    assert parent_id_laptops[0] == 1, f"Laptops parent_id should be 1, got {parent_id_laptops[0]}"

    # Delete the parent (Electronics); child parent_id should become NULL (ON DELETE SET NULL)
    conn.execute("DELETE FROM categories WHERE id = 1")
    conn.commit()
    laptops = conn.execute(
        "SELECT parent_id FROM categories WHERE name = 'Laptops'"
    ).fetchone()
    assert laptops is not None, "Laptops row should still exist after parent deleted"
    assert laptops[0] is None, f"Laptops parent_id should be NULL after parent deleted, got {laptops[0]}"
    conn.close()


def test_price_history_table_exists() -> None:
    """product_price_history table exists with required columns."""
    _, conn = _fresh_db()
    info = conn.execute("PRAGMA table_info(product_price_history)").fetchall()
    conn.close()
    col_names = [row[1] for row in info]
    assert "id" in col_names, "product_price_history.id missing"
    assert "product_id" in col_names, "product_price_history.product_id missing"
    assert "old_price" in col_names, "product_price_history.old_price missing"
    assert "new_price" in col_names, "product_price_history.new_price missing"
    assert "changed_at" in col_names, "product_price_history.changed_at missing"


def test_price_logging_fires() -> None:
    """Updating a product's price inserts a row into product_price_history."""
    _, conn = _fresh_db()
    conn.execute(
        "INSERT INTO products (id, name, category, price, stock) "
        "VALUES (1, 'Widget', 'Test', 10.0, 100)"
    )
    conn.commit()
    conn.execute("UPDATE products SET price = 50.0 WHERE id = 1")
    conn.commit()

    rows = conn.execute(
        "SELECT COUNT(*) FROM product_price_history WHERE product_id = 1"
    ).fetchone()[0]
    conn.close()
    assert rows == 1, (
        f"Expected 1 history row after price update, got {rows}. "
        "Check that trg_log_price_change exists and fires correctly."
    )


if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
