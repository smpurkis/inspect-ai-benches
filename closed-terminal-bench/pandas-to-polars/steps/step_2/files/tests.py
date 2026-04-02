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

PUBLIC_DATA = STEP1_FILES / "public_data"
STEP1_EXPECTED = PUBLIC_DATA / "expected"
STEP2_EXPECTED = BASE / "public_data" / "expected"

INPUT_DIR = PUBLIC_DATA
OUT_DIR = Path("/tmp/pandas_to_polars_step2_visible")

PUBLIC_EXPECTED_ANALYTICS_SHA256 = (
    "dcf3279b42a57a5a8194d1fada11bc05df6cb66bf81f29196f4f712e9beaba5b"
)
PUBLIC_EXPECTED_COUNTRY_SHA256 = (
    "eb0d358d2f7228cb9a690cac30bad5d8ef1eb9b3f10bde80b4eae459d640a482"
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


def test_step2_merchant_analytics_has_window_columns(pipeline_output) -> None:
    """merchant_analytics.parquet must contain the required window/rolling columns."""
    df = pl.read_parquet(pipeline_output / "merchant_analytics.parquet")
    required = {
        "rolling_30d_revenue", "revenue_rank", "qa_quartile",
        "revenue_zscore", "anomaly_flag", "monthly_cumulative_revenue",
        "mom_revenue_growth",
    }
    missing = required - set(df.columns)
    assert not missing, (
        f"merchant_analytics.parquet is missing required window columns: {sorted(missing)}"
    )


def test_step2_merchant_analytics_schema(pipeline_output) -> None:
    """merchant_analytics.parquet must have the expected column names and order."""
    actual = pl.read_parquet(pipeline_output / "merchant_analytics.parquet")
    expected = pl.read_parquet(STEP2_EXPECTED / "merchant_analytics.parquet")
    assert actual.columns == expected.columns, (
        f"columns differ: {actual.columns} vs {expected.columns}"
    )


def test_step2_merchant_analytics_sort_order(pipeline_output) -> None:
    """merchant_analytics.parquet must be sorted by [merchant_id, event_date, row_id]."""
    df = pl.read_parquet(pipeline_output / "merchant_analytics.parquet")
    sort_cols = ["merchant_id", "event_date", "row_id"]
    for col in sort_cols:
        assert col in df.columns, f"missing sort column: {col}"
    df_sorted = df.sort(sort_cols)
    assert df.frame_equal(df_sorted), (
        "merchant_analytics.parquet is not sorted by [merchant_id, event_date, row_id]"
    )


def test_step2_country_summary_schema(pipeline_output) -> None:
    """country_summary.parquet must have the expected column names and order."""
    actual = pl.read_parquet(pipeline_output / "country_summary.parquet")
    expected = pl.read_parquet(STEP2_EXPECTED / "country_summary.parquet")
    assert actual.columns == expected.columns, (
        f"columns differ: {actual.columns} vs {expected.columns}"
    )


def test_step2_country_summary_has_concentration_metrics(pipeline_output) -> None:
    """country_summary.parquet must contain the required concentration metric columns."""
    df = pl.read_parquet(pipeline_output / "country_summary.parquet")
    required = {
        "hhi", "top3_merchant_share", "gini_coefficient",
        "median_merchant_revenue", "premium_revenue_share",
    }
    missing = required - set(df.columns)
    assert not missing, (
        f"country_summary.parquet is missing required concentration columns: {sorted(missing)}"
    )


def test_step2_merchant_analytics_matches(pipeline_output) -> None:
    _assert_parquet_equal(
        pipeline_output / "merchant_analytics.parquet",
        STEP2_EXPECTED / "merchant_analytics.parquet",
    )


def test_step2_country_summary_matches(pipeline_output) -> None:
    _assert_parquet_equal(
        pipeline_output / "country_summary.parquet",
        STEP2_EXPECTED / "country_summary.parquet",
    )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
