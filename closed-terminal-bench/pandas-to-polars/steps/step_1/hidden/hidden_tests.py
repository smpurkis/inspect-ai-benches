#!/usr/bin/env python3

import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal


BASE = Path(__file__).resolve().parent
STEP1_FILES = BASE.parent / "files"
HIDDEN_DATA = BASE / "hidden_data"
EXPECTED = HIDDEN_DATA / "expected"

CANDIDATE = STEP1_FILES / "pipeline_polars.py"
INPUT_DIR = HIDDEN_DATA
OUT_DIR = Path("/tmp/pandas_to_polars_step1_hidden")

HIDDEN_INPUT_SHA256 = "3c7eae2d597406b6d47e98da0963bf5cd427136a9e8386a35c01ba157c2d7fb2"
HIDDEN_EXPECTED_CSV_SHA256 = (
    "f99177d970fd5bdf820a1ff1d42ad215f3d7b293ee23571f69deb06b885c8f81"
)
HIDDEN_EXPECTED_JSON_SHA256 = (
    "4167ba80ecf4a4deb09b579fc5817ef7f87d2c4011cce4d7840a76a344c0aea0"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_parquet_equal(actual: Path, expected: Path, rtol: float = 1e-5) -> None:
    df_a = pl.read_parquet(actual)
    df_e = pl.read_parquet(expected)
    assert_frame_equal(df_a, df_e, check_exact=False, check_dtype=False, rtol=rtol)


def _assert_csv_equal(actual: Path, expected: Path, rtol: float = 1e-5) -> None:
    df_a = pl.read_csv(actual)
    df_e = pl.read_csv(expected)
    assert_frame_equal(df_a, df_e, check_exact=False, check_dtype=False, rtol=rtol)


def _assert_json_equal(actual: Path, expected: Path, rtol: float = 1e-5) -> None:
    a = json.loads(actual.read_text(encoding="utf-8"))
    e = json.loads(expected.read_text(encoding="utf-8"))
    assert type(a) is type(e), f"type mismatch: {type(a)} vs {type(e)}"
    if isinstance(e, dict):
        assert set(a.keys()) == set(e.keys()), (
            f"keys differ: {set(a.keys()) ^ set(e.keys())}"
        )
        for k in e:
            if isinstance(e[k], float):
                assert math.isclose(a[k], e[k], rel_tol=rtol), f"{k}: {a[k]} != {e[k]}"
            else:
                assert a[k] == e[k], f"{k}: {a[k]!r} != {e[k]!r}"
    else:
        assert a == e


def _run_candidate(out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        ["python3", str(CANDIDATE), "--in", str(INPUT_DIR), "--out", str(out_dir)]
    )


@pytest.fixture(scope="module")
def pipeline_output():
    """Run the candidate pipeline once for all tests in this module."""
    assert CANDIDATE.exists(), "Missing /app/step_1/files/pipeline_polars.py"
    _run_candidate(OUT_DIR)
    return OUT_DIR


# ── Tests ─────────────────────────────────────────────────────────────────


def test_step1_hidden_fixture_integrity() -> None:
    assert _sha256(HIDDEN_DATA / "input.parquet") == HIDDEN_INPUT_SHA256
    assert _sha256(EXPECTED / "top_merchants.csv") == HIDDEN_EXPECTED_CSV_SHA256
    assert _sha256(EXPECTED / "quality.json") == HIDDEN_EXPECTED_JSON_SHA256


def test_step1_hidden_output_schemas(pipeline_output) -> None:
    """Column names and order of each output must match expected."""
    out = pipeline_output
    for name, reader in [
        ("summary.parquet", pl.read_parquet),
        ("top_merchants.csv", pl.read_csv),
    ]:
        actual = reader(out / name)
        expected = reader(EXPECTED / name)
        assert actual.columns == expected.columns, (
            f"{name} columns differ: {actual.columns} vs {expected.columns}"
        )


def test_step1_hidden_row_counts(pipeline_output) -> None:
    """Row counts of each tabular output must match expected."""
    out = pipeline_output
    for name, reader in [
        ("summary.parquet", pl.read_parquet),
        ("top_merchants.csv", pl.read_csv),
    ]:
        actual = reader(out / name)
        expected = reader(EXPECTED / name)
        assert len(actual) == len(expected), (
            f"{name} row count: got {len(actual)}, expected {len(expected)}"
        )


def test_step1_hidden_uses_polars_not_pandas() -> None:
    """The candidate script must not import pandas."""
    assert CANDIDATE.exists(), "Missing /app/step_1/files/pipeline_polars.py"
    source = CANDIDATE.read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "import pandas" not in stripped, (
            f"pipeline_polars.py must not use pandas: {stripped}"
        )


def test_step1_hidden_summary_parquet_matches(pipeline_output) -> None:
    _assert_parquet_equal(pipeline_output / "summary.parquet", EXPECTED / "summary.parquet")


def test_step1_hidden_top_merchants_csv_matches(pipeline_output) -> None:
    _assert_csv_equal(pipeline_output / "top_merchants.csv", EXPECTED / "top_merchants.csv")


def test_step1_hidden_quality_json_matches(pipeline_output) -> None:
    _assert_json_equal(pipeline_output / "quality.json", EXPECTED / "quality.json")


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
