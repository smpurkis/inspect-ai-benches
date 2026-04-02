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
PUBLIC_DATA = BASE / "public_data"
EXPECTED = PUBLIC_DATA / "expected"

CANDIDATE = BASE / "pipeline_polars.py"
INPUT_DIR = PUBLIC_DATA
OUT_DIR = Path("/tmp/pandas_to_polars_step1_visible")

PUBLIC_INPUT_SHA256 = "e468e0bc1f8c082c21c01be35e864f1a5a381f01ef6faae72136b57954ea8c35"
PUBLIC_EXPECTED_CSV_SHA256 = (
    "8f641caa49d1fe852d3a843c3bf13bf187ccad3d977f9c938b437259c5f13d45"
)
PUBLIC_EXPECTED_JSON_SHA256 = (
    "71f80bc2b15260b81137fcc80d4b4d00236d26f124f6c62b30234c3864dc7bca"
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


def test_step1_public_fixture_integrity() -> None:
    assert _sha256(PUBLIC_DATA / "input.parquet") == PUBLIC_INPUT_SHA256
    assert _sha256(EXPECTED / "top_merchants.csv") == PUBLIC_EXPECTED_CSV_SHA256
    assert _sha256(EXPECTED / "quality.json") == PUBLIC_EXPECTED_JSON_SHA256


def test_step1_output_schemas(pipeline_output) -> None:
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


def test_step1_deterministic_reruns() -> None:
    """Running the pipeline twice must produce byte-identical outputs."""
    assert CANDIDATE.exists(), "Missing /app/step_1/files/pipeline_polars.py"
    dir_a = Path("/tmp/pandas_to_polars_step1_det_a")
    dir_b = Path("/tmp/pandas_to_polars_step1_det_b")
    _run_candidate(dir_a)
    _run_candidate(dir_b)
    for name in ("summary.parquet", "top_merchants.csv", "quality.json"):
        a = (dir_a / name).read_bytes()
        b = (dir_b / name).read_bytes()
        assert a == b, f"{name} differs between runs"


def test_step1_uses_polars_not_pandas() -> None:
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


def test_step1_summary_parquet_matches(pipeline_output) -> None:
    _assert_parquet_equal(pipeline_output / "summary.parquet", EXPECTED / "summary.parquet")


def test_step1_top_merchants_csv_matches(pipeline_output) -> None:
    _assert_csv_equal(pipeline_output / "top_merchants.csv", EXPECTED / "top_merchants.csv")


def test_step1_quality_json_matches(pipeline_output) -> None:
    _assert_json_equal(pipeline_output / "quality.json", EXPECTED / "quality.json")


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
