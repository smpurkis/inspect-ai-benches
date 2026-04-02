import pathlib
import shutil
import sqlite3
import subprocess

DB_PATH = pathlib.Path("/app/db.sqlite")
OPT_SQL = pathlib.Path("/app/optimize.sql")
PLAN_REQUIREMENTS = pathlib.Path("/app/plan_requirements.txt")
QUERY = pathlib.Path("/app/query.sql")


def load_query(path: pathlib.Path) -> str:
    return path.read_text()


def explain(db_path: pathlib.Path, query: str) -> str:
    proc = subprocess.run(
        ["sqlite3", str(db_path), f"EXPLAIN QUERY PLAN {query}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


def copy_db(tmp_path: pathlib.Path, name: str) -> pathlib.Path:
    target = tmp_path / name
    shutil.copyfile(DB_PATH, target)
    return target


def test_optimize_sql_exists():
    assert OPT_SQL.exists(), "optimize.sql missing"


def test_db_snapshot_present():
    assert DB_PATH.exists(), "db.sqlite missing"
    assert DB_PATH.stat().st_size > 0, "db.sqlite is empty"


def test_results_match(tmp_path):
    baseline_db = copy_db(tmp_path, "baseline.sqlite")
    optimized_db = copy_db(tmp_path, "optimized.sqlite")
    with sqlite3.connect(baseline_db) as conn:
        baseline = list(conn.execute(load_query(QUERY)))
    with sqlite3.connect(optimized_db) as conn:
        conn.executescript(OPT_SQL.read_text())
        optimized = list(conn.execute(load_query(QUERY)))
    assert baseline == optimized, "optimized query results differ"


def test_plan_meets_requirements(tmp_path):
    optimized_db = copy_db(tmp_path, "plan.sqlite")
    with sqlite3.connect(optimized_db) as conn:
        conn.executescript(OPT_SQL.read_text())
    plan = explain(optimized_db, load_query(QUERY))
    for requirement in PLAN_REQUIREMENTS.read_text().splitlines():
        requirement = requirement.strip()
        if not requirement:
            continue
        assert requirement in plan, f"missing plan requirement: {requirement}"
