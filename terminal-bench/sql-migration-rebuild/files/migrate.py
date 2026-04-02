#!/usr/bin/env python3
"""Migration runner — applies all .sql files in order.

This file is correct and should NOT be modified.
"""
import sqlite3
import sys
import pathlib


def migrate(db_path, migrations_dir):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    migrations = sorted(pathlib.Path(migrations_dir).glob("*.sql"))
    for mig in migrations:
        sql = mig.read_text()
        conn.executescript(sql)
    conn.close()


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "/tmp/bench.db"
    migrate(db, str(pathlib.Path(__file__).parent / "migrations"))
    print(f"Migrations applied to {db}")
