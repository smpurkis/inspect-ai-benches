"""Generated and metamorphic tests with an independent Python row oracle."""

import csv
import datetime as dt
import io
import json
import os
import pathlib
import pwd
import random
import shutil
import subprocess
import tempfile

import pytest

UTC = dt.timezone.utc
BASE = dt.datetime(2024, 1, 1, tzinfo=UTC)


@pytest.fixture(scope="session", autouse=True)
def postgres_server():
    root = pathlib.Path(tempfile.mkdtemp(prefix="bitemporal-hidden-pg-"))
    data = root / "data"
    socket = root / "socket"
    socket.mkdir()
    postgres = pwd.getpwnam("postgres")
    for path in (root, socket):
        os.chown(path, postgres.pw_uid, postgres.pw_gid)

    pg_ctl = "/usr/lib/postgresql/16/bin/pg_ctl"
    subprocess.run([
        "runuser", "-u", "postgres", "--", "/usr/lib/postgresql/16/bin/initdb",
        "-D", str(data), "--no-locale", "--encoding=UTF8", "--auth=trust",
    ], check=True, capture_output=True)
    subprocess.run([
        "runuser", "-u", "postgres", "--", pg_ctl, "-D", str(data),
        "-o", f"-F -k {socket} -p 55441 -h ''", "-w", "start",
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    names = ("PGHOST", "PGPORT", "PGUSER", "PGDATABASE")
    previous = {name: os.environ.get(name) for name in names}
    os.environ.update(PGHOST=str(socket), PGPORT="55441", PGUSER="postgres", PGDATABASE="postgres")
    try:
        subprocess.run([
            "psql", "-X", "-v", "ON_ERROR_STOP=1", "-q", "-f", "/app/files/schema.sql",
        ], check=True)
        yield
    finally:
        subprocess.run([
            "runuser", "-u", "postgres", "--", pg_ctl, "-D", str(data),
            "-m", "fast", "-w", "stop",
        ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        shutil.rmtree(root, ignore_errors=True)
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def pg(statement: str) -> None:
    subprocess.run(["psql", "-X", "-v", "ON_ERROR_STOP=1", "-q"], input=statement,
                   text=True, capture_output=True, check=True)


def quote(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, dict):
        value = json.dumps(value, sort_keys=True)
    return "'" + str(value).replace("'", "''") + "'"


def install(rows, context):
    values = ",".join("(" + ",".join(quote(x) for x in row) + ")" for row in rows)
    ctx = ",".join(quote(x) for x in context)
    pg("TRUNCATE entitlement_history, query_context;"
       + ("INSERT INTO entitlement_history VALUES " + values + ";" if values else "")
       + "INSERT INTO query_context VALUES (" + ctx + ");")


def candidate():
    result = subprocess.run(["bash", "/app/files/run_query.sh"], text=True,
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    parsed = list(csv.reader(io.StringIO(result.stdout)))
    assert len(parsed) <= 1, "query must resolve at most one row"
    return parsed


def oracle(rows, context):
    tenant, subject, key, business, audit = context
    eligible = []
    for row in rows:
        rt, rs, rk, _, vf, vt, sf, st, _, _ = row
        if (rt, rs, rk) != (tenant, subject, key):
            continue
        if not (vf <= business and (vt is None or business < vt)):
            continue
        if not (sf <= audit and (st is None or audit < st)):
            continue
        eligible.append(row)
    if not eligible:
        return None
    winner = max(eligible, key=lambda row: (row[6], row[4], row[8]))
    return None if winner[9] else winner


def assert_answer(rows, context):
    expected = oracle(rows, context)
    actual = candidate()
    if expected is None:
        assert actual == []
    else:
        assert len(actual) == 1
        got = actual[0]
        assert got[:3] == list(expected[:3])
        assert json.loads(got[3]) == expected[3]
        assert int(got[8]) == expected[8]


def stamp(hours):
    return BASE + dt.timedelta(hours=hours)


@pytest.mark.parametrize("seed", range(12))
def test_generated_overlapping_intervals_and_ties(seed):
    rng = random.Random(0xB17E + seed)
    rows = []
    revision = 1
    for tenant in ("target", "decoy"):
        for _ in range(35):
            vf = rng.randrange(-20, 60)
            sf = rng.randrange(-20, 60)
            vt = None if rng.random() < .2 else stamp(vf + rng.randrange(1, 45))
            st = None if rng.random() < .2 else stamp(sf + rng.randrange(1, 45))
            tomb = rng.random() < .18
            rows.append((tenant, "subject", "feature", None if tomb else {"r": revision},
                         stamp(vf), vt, stamp(sf), st, revision, tomb))
            revision += 1
    # Exact valid/system ties make revision_id semantically observable.
    rows.extend([
        ("target", "subject", "feature", {"tie": 1}, stamp(0), None, stamp(0), None, 900, False),
        ("target", "subject", "feature", {"tie": 2}, stamp(0), None, stamp(0), None, 901, False),
    ])
    context = ("target", "subject", "feature", stamp(30), stamp(30))
    rng.shuffle(rows)
    install(rows, context)
    assert_answer(rows, context)


def test_all_half_open_boundaries_and_retroactive_tombstone():
    rows = [
        ("t", "s", "k", {"expired-valid": 1}, stamp(0), stamp(10), stamp(0), None, 1, False),
        ("t", "s", "k", {"expired-system": 1}, stamp(10), None, stamp(0), stamp(20), 2, False),
        ("t", "s", "k", None, stamp(10), None, stamp(20), None, 3, True),
    ]
    context = ("t", "s", "k", stamp(10), stamp(20))
    install(rows, context)
    assert_answer(rows, context)


def test_exact_ties_are_broken_by_revision_not_insertion_order():
    rows = [
        ("t", "s", "k", {"revision": 42}, stamp(0), None, stamp(0), None, 42, False),
        ("t", "s", "k", {"revision": 41}, stamp(0), None, stamp(0), None, 41, False),
    ]
    context = ("t", "s", "k", stamp(1), stamp(1))
    install(list(reversed(rows)), context)
    assert_answer(rows, context)
    assert json.loads(candidate()[0][3]) == {"revision": 42}


def test_metamorphic_decoys_reordering_and_time_translation():
    rows = [
        ("t", "s", "k", {"old": 1}, stamp(0), None, stamp(0), stamp(8), 1, False),
        ("t", "s", "k", {"new": 1}, stamp(-2), stamp(40), stamp(8), None, 2, False),
    ]
    context = ("t", "s", "k", stamp(12), stamp(12))
    install(rows, context)
    baseline = candidate()
    decoys = rows + [
        ("x", "s", "k", {"decoy": 1}, stamp(-100), None, stamp(100), None, 9999, False),
        ("t", "other", "k", {"decoy": 2}, stamp(-100), None, stamp(100), None, 9998, False),
        ("t", "s", "other", {"decoy": 3}, stamp(-100), None, stamp(100), None, 9997, False),
    ]
    install(list(reversed(decoys)), context)
    assert candidate() == baseline

    delta = dt.timedelta(days=731)
    shifted = [row[:4] + tuple(x + delta if x is not None else None for x in row[4:8]) + row[8:]
               for row in rows]
    shifted_context = context[:3] + (context[3] + delta, context[4] + delta)
    install(shifted, shifted_context)
    assert candidate()[0][3] == baseline[0][3]


def test_query_is_read_only_single_statement_and_reaches_kernel():
    source = open("/app/files/query.sql", encoding="utf-8").read()
    lowered = source.lower()
    forbidden = ("insert ", "update ", "delete ", "drop ", "alter ", "create ",
                 "truncate ", "grant ", "revoke ", "set ", "copy ", "do $$", "call ",
                 "pg_read_file", "program")
    assert not any(token in lowered for token in forbidden)
    assert ";" not in source.strip().rstrip(";"), "submit exactly one SQL statement"
    assert "entitlement_history" in lowered and "query_context" in lowered
    rows = [("t", "s", "k", {"reachable": True}, stamp(0), None, stamp(0), None, 1, False)]
    context = ("t", "s", "k", stamp(1), stamp(1))
    install(rows, context)
    assert json.loads(candidate()[0][3]) == {"reachable": True}
