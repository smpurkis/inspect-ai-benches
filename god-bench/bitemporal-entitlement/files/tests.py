"""Four-category public feedback for the bitemporal query contract."""

import atexit
import csv
import io
import json
import os
import pathlib
import pwd
import subprocess


def _ensure_postgres():
    if os.environ.get("PGHOST"):
        return
    root = pathlib.Path("/tmp/bitemporal-public-pg")
    data = root / "data"
    socket = root / "socket"
    socket.mkdir(parents=True, exist_ok=True)
    postgres = pwd.getpwnam("postgres")
    for path in (root, socket):
        os.chown(path, postgres.pw_uid, postgres.pw_gid)
    if not (data / "PG_VERSION").exists():
        subprocess.run([
            "runuser", "-u", "postgres", "--", "/usr/lib/postgresql/16/bin/initdb",
            "-D", str(data), "--no-locale", "--encoding=UTF8", "--auth=trust",
        ], check=True, capture_output=True)
    subprocess.run([
        "runuser", "-u", "postgres", "--", "/usr/lib/postgresql/16/bin/pg_ctl",
        "-D", str(data), "-o", f"-F -k {socket} -p 55440 -h ''", "-w", "start",
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.environ.update(PGHOST=str(socket), PGPORT="55440", PGUSER="postgres", PGDATABASE="postgres")
    atexit.register(lambda: subprocess.run([
        "runuser", "-u", "postgres", "--", "/usr/lib/postgresql/16/bin/pg_ctl",
        "-D", str(data), "-m", "fast", "-w", "stop",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15))
    subprocess.run(["psql", "-X", "-v", "ON_ERROR_STOP=1", "-q", "-f", "/app/files/schema.sql"], check=True)


_ensure_postgres()


def sql(statement: str) -> None:
    subprocess.run(
        ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-q"],
        input=statement,
        text=True,
        check=True,
        capture_output=True,
    )


def query():
    result = subprocess.run(
        ["bash", "/app/files/run_query.sh"],
        check=True,
        text=True,
        capture_output=True,
    )
    return list(csv.reader(io.StringIO(result.stdout)))


def reset(rows: str, context: str) -> None:
    sql("TRUNCATE entitlement_history, query_context;" + rows + context)


def test_normal_current_correction():
    reset(
        """INSERT INTO entitlement_history VALUES
        ('acme','u1','deploy','{"level":1}','2025-01-01','2026-01-01','2025-01-02','2025-03-01',1,false),
        ('acme','u1','deploy','{"level":2}','2025-01-01','2026-01-01','2025-03-01',NULL,2,false);""",
        "INSERT INTO query_context VALUES ('acme','u1','deploy','2025-06-01','2025-04-01');",
    )
    rows = query()
    assert len(rows) == 1
    assert json.loads(rows[0][3]) == {"level": 2}
    assert rows[0][8] == "2"


def test_edge_half_open_boundary_and_tombstone():
    reset(
        """INSERT INTO entitlement_history VALUES
        ('acme','u1','deploy','{"old":true}','2025-01-01','2025-02-01','2025-01-01',NULL,1,false),
        ('acme','u1','deploy',NULL,'2025-02-01',NULL,'2025-01-01',NULL,2,true);""",
        "INSERT INTO query_context VALUES ('acme','u1','deploy','2025-02-01','2025-02-01');",
    )
    assert query() == []


def test_invariant_tenant_and_key_isolation():
    reset(
        """INSERT INTO entitlement_history VALUES
        ('other','u1','deploy','{"wrong":1}','2020-01-01',NULL,'2020-01-01',NULL,99,false),
        ('acme','u1','billing','{"wrong":2}','2020-01-01',NULL,'2020-01-01',NULL,98,false),
        ('acme','u1','deploy','{"right":true}','2020-01-01',NULL,'2020-01-01',NULL,1,false);""",
        "INSERT INTO query_context VALUES ('acme','u1','deploy','2025-01-01','2025-01-01');",
    )
    assert json.loads(query()[0][3]) == {"right": True}


def test_deterministic_rerun_with_exact_ties():
    reset(
        """INSERT INTO entitlement_history VALUES
        ('acme','u1','deploy','{"winner":false}','2020-01-01',NULL,'2024-01-01',NULL,7,false),
        ('acme','u1','deploy','{"winner":true}','2020-01-01',NULL,'2024-01-01',NULL,8,false);""",
        "INSERT INTO query_context VALUES ('acme','u1','deploy','2025-01-01','2025-01-01');",
    )
    first = query()
    assert first == query()
    assert json.loads(first[0][3]) == {"winner": True}
