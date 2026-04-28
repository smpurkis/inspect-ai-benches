#!/usr/bin/env python3

import hashlib
import json
import math
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal


BASE = Path(__file__).resolve().parent
STEP1_FILES = BASE
CANDIDATE = STEP1_FILES / "pipeline_polars.py"

# V1 paths (for regression)
V1_INPUT = STEP1_FILES / "public_data"
STEP1_EXPECTED = V1_INPUT / "expected"
STEP2_EXPECTED = BASE / "public_data" / "expected"

# V2 paths
V2_DATA = BASE / "public_data"
STEP3_EXPECTED = V2_DATA / "expected"

OUT_DIR_V1 = Path("/tmp/pandas_to_polars_step3_v1_visible")
OUT_DIR_V2 = Path("/tmp/pandas_to_polars_step3_v2_visible")

# SHA256 of expected v2 outputs
PUBLIC_EXPECTED_ENRICHED_SHA256 = (
    "450d71eecc5c5b43bbeb9ffdde1b3adfe91ba2948c708f47d3b9db3ad0d9c8f3"
)
PUBLIC_EXPECTED_QUARANTINE_SHA256 = (
    "2b34815e1bf11fe42f49c4586ece8d50dcf93924343b1168ca320b24681b8862"
)
PUBLIC_EXPECTED_QUALITY_V2_SHA256 = (
    "c3c57fa9634fc3a62a021cbb5038778b60a4b09a2be604bbbedf93f7ffc008d6"
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
            elif isinstance(e[k], dict):
                for kk in e[k]:
                    assert a[k].get(kk) == e[k][kk], (
                        f"{k}.{kk}: {a[k].get(kk)!r} != {e[k][kk]!r}"
                    )
            else:
                assert a[k] == e[k], f"{k}: {a[k]!r} != {e[k]!r}"
    else:
        assert a == e


def _run_candidate(input_dir: Path, output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        ["python3", str(CANDIDATE), "--in", str(input_dir), "--out", str(output_dir)]
    )


def _run_candidate_with_lazy_enforcement(input_dir: Path, output_dir: Path) -> None:
    """Run pipeline in a subprocess with pl.read_parquet/read_csv monkey-patched to fail."""
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    wrapper = textwrap.dedent(f"""\
        import sys
        import polars as pl

        def _blocked_read_parquet(*a, **kw):
            raise RuntimeError(
                "pl.read_parquet is banned in step 3. Use pl.scan_parquet for lazy execution."
            )

        def _blocked_read_csv(*a, **kw):
            raise RuntimeError(
                "pl.read_csv is banned in step 3. Use pl.scan_csv for lazy execution."
            )

        pl.read_parquet = _blocked_read_parquet
        pl.read_csv = _blocked_read_csv

        sys.argv = [
            "pipeline_polars.py",
            "--in", "{input_dir}",
            "--out", "{output_dir}",
        ]

        sys.path.insert(0, "{STEP1_FILES}")
        import pipeline_polars
        pipeline_polars.main()
    """)

    wrapper_path = Path("/tmp/_lazy_enforcer_step3_visible.py")
    wrapper_path.write_text(wrapper)

    subprocess.check_call(
        [sys.executable, str(wrapper_path)],
        timeout=120,
    )


@pytest.fixture(scope="module")
def v2_pipeline_output():
    """Run the candidate pipeline once with v2 data."""
    assert CANDIDATE.exists(), "Missing /app/files/pipeline_polars.py"
    _run_candidate(V2_DATA, OUT_DIR_V2)
    return OUT_DIR_V2


@pytest.fixture(scope="module")
def v1_pipeline_output():
    """Run the candidate pipeline with v1 data under lazy enforcement."""
    assert CANDIDATE.exists(), "Missing /app/files/pipeline_polars.py"
    _run_candidate_with_lazy_enforcement(V1_INPUT, OUT_DIR_V1)
    return OUT_DIR_V1


# ── Tests ─────────────────────────────────────────────────────────────────


def test_step3_quarantine_has_valid_error_codes(v2_pipeline_output) -> None:
    """quarantine.parquet error_code column must only contain valid error codes."""
    df = pl.read_parquet(v2_pipeline_output / "quarantine.parquet")
    assert "error_code" in df.columns, (
        "quarantine.parquet is missing 'error_code' column"
    )
    valid_codes = {
        "NULL_REQUIRED", "INVALID_DATE", "NEGATIVE_AMOUNT",
        "MISSING_MERCHANT", "INACTIVE_MERCHANT",
    }
    actual_codes = set(df["error_code"].drop_nulls().unique().to_list())
    invalid = actual_codes - valid_codes
    assert not invalid, (
        f"quarantine.parquet has invalid error codes: {sorted(invalid)}. "
        f"Valid codes are: {sorted(valid_codes)}"
    )
    assert len(actual_codes) > 0, "quarantine.parquet error_code column is empty"


def test_step3_enriched_transactions_matches(v2_pipeline_output) -> None:
    _assert_parquet_equal(
        v2_pipeline_output / "enriched_transactions.parquet",
        STEP3_EXPECTED / "enriched_transactions.parquet",
    )


def test_step3_quarantine_matches(v2_pipeline_output) -> None:
    _assert_parquet_equal(
        v2_pipeline_output / "quarantine.parquet",
        STEP3_EXPECTED / "quarantine.parquet",
    )


def test_step3_quality_v2_json_matches(v2_pipeline_output) -> None:
    _assert_json_equal(
        v2_pipeline_output / "quality_v2.json",
        STEP3_EXPECTED / "quality_v2.json",
    )


def test_step3_lazy_execution_enforced_v2() -> None:
    """Pipeline must use scan_parquet/scan_csv, not read_parquet/read_csv."""
    assert CANDIDATE.exists()
    lazy_dir = Path("/tmp/pandas_to_polars_step3_v2_lazy_visible")
    _run_candidate_with_lazy_enforcement(V2_DATA, lazy_dir)
    _assert_parquet_equal(
        lazy_dir / "enriched_transactions.parquet",
        STEP3_EXPECTED / "enriched_transactions.parquet",
    )


def test_step3_v1_step1_outputs_regression(v1_pipeline_output) -> None:
    _assert_parquet_equal(
        v1_pipeline_output / "summary.parquet", STEP1_EXPECTED / "summary.parquet"
    )
    _assert_csv_equal(
        v1_pipeline_output / "top_merchants.csv", STEP1_EXPECTED / "top_merchants.csv"
    )
    _assert_json_equal(
        v1_pipeline_output / "quality.json", STEP1_EXPECTED / "quality.json"
    )


def test_step3_v1_step2_outputs_regression(v1_pipeline_output) -> None:
    _assert_parquet_equal(
        v1_pipeline_output / "merchant_analytics.parquet",
        STEP2_EXPECTED / "merchant_analytics.parquet",
    )
    _assert_parquet_equal(
        v1_pipeline_output / "country_summary.parquet",
        STEP2_EXPECTED / "country_summary.parquet",
    )


# ── New complexity tests ─────────────────────────────────────────────────


def test_session_analytics_exists(v1_pipeline_output) -> None:
    """session_analytics.parquet must exist and have expected columns."""
    path = v1_pipeline_output / "session_analytics.parquet"
    assert path.exists(), "Missing session_analytics.parquet"
    df = pl.read_parquet(path)
    expected_cols = {
        "session_id", "merchant_id", "session_start", "session_end",
        "session_revenue", "event_count", "session_duration_days",
    }
    actual_cols = set(df.columns)
    missing = expected_cols - actual_cols
    assert not missing, f"session_analytics.parquet is missing columns: {sorted(missing)}"
    assert len(df) > 0, "session_analytics.parquet is empty"


def test_session_analytics_matches(v1_pipeline_output) -> None:
    """session_analytics.parquet values must match expected output."""
    _assert_parquet_equal(
        v1_pipeline_output / "session_analytics.parquet",
        STEP2_EXPECTED / "session_analytics.parquet",
    )


def test_promotion_impact_matches(v1_pipeline_output) -> None:
    """promotion_impact.parquet values must match expected output."""
    _assert_parquet_equal(
        v1_pipeline_output / "promotion_impact.parquet",
        STEP2_EXPECTED / "promotion_impact.parquet",
    )


def test_pivot_revenue_structure(v1_pipeline_output) -> None:
    """pivot_revenue.parquet must have correct shape (months x countries)."""
    path = v1_pipeline_output / "pivot_revenue.parquet"
    assert path.exists(), "Missing pivot_revenue.parquet"
    df = pl.read_parquet(path)
    assert "event_month" in df.columns, "Missing event_month column"
    # Should have 8 country columns + event_month = 9 total
    expected_countries = {"AU", "CA", "DE", "FR", "GB", "IN", "JP", "US"}
    actual_countries = set(df.columns) - {"event_month"}
    missing = expected_countries - actual_countries
    assert not missing, f"pivot_revenue.parquet missing country columns: {sorted(missing)}"
    # No NaN values - should all be 0.0 for missing combos
    for col in expected_countries:
        null_count = df[col].null_count()
        assert null_count == 0, f"pivot_revenue.parquet has {null_count} NaN values in {col}"


def test_pivot_revenue_matches(v1_pipeline_output) -> None:
    """pivot_revenue.parquet values must match expected output."""
    _assert_parquet_equal(
        v1_pipeline_output / "pivot_revenue.parquet",
        STEP2_EXPECTED / "pivot_revenue.parquet",
    )


def test_weighted_p90_exists_in_summary(v1_pipeline_output) -> None:
    """summary.parquet must contain the weighted_p90_revenue column."""
    df = pl.read_parquet(v1_pipeline_output / "summary.parquet")
    assert "weighted_p90_revenue" in df.columns, (
        "summary.parquet is missing weighted_p90_revenue column"
    )
    assert df["weighted_p90_revenue"].null_count() == 0, (
        "weighted_p90_revenue has null values"
    )


def test_new_analytics_columns_in_merchant_analytics(v1_pipeline_output) -> None:
    """merchant_analytics.parquet must have the new window function columns."""
    df = pl.read_parquet(v1_pipeline_output / "merchant_analytics.parquet")
    new_cols = [
        "ewma_qa_score", "mom_revenue_growth_2m",
        "cohort_relative_revenue", "intra_month_variance",
    ]
    missing = [c for c in new_cols if c not in df.columns]
    assert not missing, f"merchant_analytics.parquet missing columns: {missing}"


def test_country_summary_new_columns(v1_pipeline_output) -> None:
    """country_summary.parquet must have bucket_entropy and population_std_revenue."""
    df = pl.read_parquet(v1_pipeline_output / "country_summary.parquet")
    new_cols = ["bucket_entropy", "population_std_revenue"]
    missing = [c for c in new_cols if c not in df.columns]
    assert not missing, f"country_summary.parquet missing columns: {missing}"


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
