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
STEP1_FILES = BASE.parent.parent / "step_1" / "files"
CANDIDATE = STEP1_FILES / "pipeline_polars.py"

HIDDEN_DATA = BASE.parent.parent / "step_1" / "hidden" / "hidden_data"
STEP1_EXPECTED = HIDDEN_DATA / "expected"
STEP2_EXPECTED = BASE / "hidden_data" / "expected"

INPUT_DIR = HIDDEN_DATA
OUT_DIR = Path("/tmp/pandas_to_polars_step2_hidden")

HIDDEN_EXPECTED_ANALYTICS_SHA256 = (
    "8bc718a8f3cf392fadd992deec61c01628520d5261ce885da671313018e35a46"
)
HIDDEN_EXPECTED_COUNTRY_SHA256 = (
    "30646e83e045cdd95c3c2f1989484316cd435bf3bda6877b39cda17f9410167f"
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
                assert math.isclose(a[k], e[k], rel_tol=rtol), (
                    f"{k}: {a[k]} != {e[k]}"
                )
            else:
                assert a[k] == e[k], f"{k}: {a[k]!r} != {e[k]!r}"
    else:
        assert a == e


def _run_candidate() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        ["python3", str(CANDIDATE), "--in", str(INPUT_DIR), "--out", str(OUT_DIR)]
    )


@pytest.fixture(scope="module")
def pipeline_output():
    """Run the candidate pipeline once for all tests in this module."""
    assert CANDIDATE.exists(), "Missing /app/step_1/files/pipeline_polars.py"
    _run_candidate()
    return OUT_DIR


# ── Tests ─────────────────────────────────────────────────────────────────


def test_step2_hidden_anomaly_flags_present(pipeline_output) -> None:
    """merchant_analytics anomaly_flag column must exist and have both True and False values."""
    df = pl.read_parquet(pipeline_output / "merchant_analytics.parquet")
    assert "anomaly_flag" in df.columns, (
        "merchant_analytics.parquet is missing 'anomaly_flag' column"
    )
    values = df["anomaly_flag"].drop_nulls().unique().to_list()
    assert True in values and False in values, (
        f"anomaly_flag should have both True and False values, got unique values: {values}"
    )


def test_step2_hidden_merchant_analytics_row_count(pipeline_output) -> None:
    """Row count catches duplication or data loss."""
    actual = pl.read_parquet(pipeline_output / "merchant_analytics.parquet")
    expected = pl.read_parquet(STEP2_EXPECTED / "merchant_analytics.parquet")
    assert len(actual) == len(expected), (
        f"merchant_analytics row count: got {len(actual)}, expected {len(expected)}"
    )


def test_step2_hidden_country_summary_row_count(pipeline_output) -> None:
    """Number of countries must match expected."""
    actual = pl.read_parquet(pipeline_output / "country_summary.parquet")
    expected = pl.read_parquet(STEP2_EXPECTED / "country_summary.parquet")
    assert len(actual) == len(expected), (
        f"country_summary row count: got {len(actual)}, expected {len(expected)}"
    )


def test_step2_hidden_gini_coefficient_in_valid_range(pipeline_output) -> None:
    """All gini_coefficient values must be in [0.0, 1.0]."""
    df = pl.read_parquet(pipeline_output / "country_summary.parquet")
    assert "gini_coefficient" in df.columns, (
        "country_summary.parquet is missing 'gini_coefficient' column"
    )
    gini = df["gini_coefficient"].drop_nulls()
    assert len(gini) > 0, "gini_coefficient column is all null"
    below = gini.filter(gini < 0.0)
    above = gini.filter(gini > 1.0)
    assert len(below) == 0, (
        f"gini_coefficient has {len(below)} value(s) below 0.0"
    )
    assert len(above) == 0, (
        f"gini_coefficient has {len(above)} value(s) above 1.0"
    )


def test_step2_hidden_merchant_analytics_matches(pipeline_output) -> None:
    _assert_parquet_equal(
        pipeline_output / "merchant_analytics.parquet",
        STEP2_EXPECTED / "merchant_analytics.parquet",
    )


def test_step2_hidden_country_summary_matches(pipeline_output) -> None:
    _assert_parquet_equal(
        pipeline_output / "country_summary.parquet",
        STEP2_EXPECTED / "country_summary.parquet",
    )


def test_step2_hidden_float_rounding(pipeline_output) -> None:
    """All float columns must be rounded to 6 decimal places."""
    for name in ("merchant_analytics.parquet", "country_summary.parquet"):
        df = pl.read_parquet(pipeline_output / name)
        for col in df.columns:
            if df[col].dtype in (pl.Float32, pl.Float64):
                values = df[col].drop_nulls()
                if len(values) == 0:
                    continue
                rounded = values.round(6)
                diff = (values - rounded).abs()
                mismatches = diff.filter(diff > 1e-10)
                assert len(mismatches) == 0, (
                    f"{name}:{col} has values not rounded to 6 decimal places"
                )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
