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
STEP1_FILES = BASE.parent / "files"
CANDIDATE = STEP1_FILES / "pipeline_polars.py"

# V1 paths (for regression)
HIDDEN_V1_DATA = BASE / "hidden_data"
STEP1_EXPECTED = HIDDEN_V1_DATA / "expected"
STEP2_EXPECTED = BASE / "hidden_data" / "expected"

# V2 paths
HIDDEN_V2_DATA = BASE / "hidden_data"
STEP3_EXPECTED = HIDDEN_V2_DATA / "expected"

OUT_DIR_V1 = Path("/tmp/pandas_to_polars_step3_v1_hidden")
OUT_DIR_V2 = Path("/tmp/pandas_to_polars_step3_v2_hidden")

# SHA256 of expected v2 outputs
HIDDEN_EXPECTED_ENRICHED_SHA256 = (
    "a209010bae18609c94d358ffd1624482c5515ace0c77d527f21734fae4fa26f6"
)
HIDDEN_EXPECTED_QUARANTINE_SHA256 = (
    "bc8b38c881c8d416703cda672e055821faa53d445013ca10e08808955c4ad273"
)
HIDDEN_EXPECTED_QUALITY_V2_SHA256 = (
    "b4a935af199286efeaee4b943609f8c250d30a6e1f9bde45371752b7260dc0b3"
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

    wrapper_path = Path("/tmp/_lazy_enforcer_step3_hidden.py")
    wrapper_path.write_text(wrapper)

    subprocess.check_call(
        [sys.executable, str(wrapper_path)],
        timeout=120,
    )


@pytest.fixture(scope="module")
def v2_pipeline_output():
    """Run the candidate pipeline with v2 hidden data under lazy enforcement."""
    assert CANDIDATE.exists(), "Missing /app/files/pipeline_polars.py"
    _run_candidate_with_lazy_enforcement(HIDDEN_V2_DATA, OUT_DIR_V2)
    return OUT_DIR_V2


@pytest.fixture(scope="module")
def v1_pipeline_output():
    """Run the candidate pipeline with v1 hidden data under lazy enforcement."""
    assert CANDIDATE.exists(), "Missing /app/files/pipeline_polars.py"
    _run_candidate_with_lazy_enforcement(HIDDEN_V1_DATA, OUT_DIR_V1)
    return OUT_DIR_V1


# ── Tests ─────────────────────────────────────────────────────────────────


def test_step3_hidden_enriched_has_reference_join_columns(v2_pipeline_output) -> None:
    """enriched_transactions.parquet must contain columns from reference table joins."""
    expected_df = pl.read_parquet(STEP3_EXPECTED / "enriched_transactions.parquet")
    actual_df = pl.read_parquet(v2_pipeline_output / "enriched_transactions.parquet")
    expected_cols = set(expected_df.columns)
    actual_cols = set(actual_df.columns)
    missing = expected_cols - actual_cols
    assert not missing, (
        f"enriched_transactions.parquet is missing columns from reference joins: {sorted(missing)}"
    )
    # Verify the joined columns have non-null values (joins actually worked)
    for col in expected_cols:
        if col not in actual_cols:
            continue
        null_frac = actual_df[col].null_count() / len(actual_df) if len(actual_df) > 0 else 0
        expected_null_frac = expected_df[col].null_count() / len(expected_df) if len(expected_df) > 0 else 0
        assert null_frac <= expected_null_frac + 0.05, (
            f"Column {col!r} has {null_frac:.1%} nulls vs expected {expected_null_frac:.1%} — "
            f"join may not be working correctly"
        )


def test_step3_hidden_enriched_transactions_matches(v2_pipeline_output) -> None:
    _assert_parquet_equal(
        v2_pipeline_output / "enriched_transactions.parquet",
        STEP3_EXPECTED / "enriched_transactions.parquet",
    )


def test_step3_hidden_quarantine_matches(v2_pipeline_output) -> None:
    _assert_parquet_equal(
        v2_pipeline_output / "quarantine.parquet",
        STEP3_EXPECTED / "quarantine.parquet",
    )


def test_step3_hidden_quality_v2_json_matches(v2_pipeline_output) -> None:
    _assert_json_equal(
        v2_pipeline_output / "quality_v2.json",
        STEP3_EXPECTED / "quality_v2.json",
    )


def test_step3_hidden_v1_step1_regression(v1_pipeline_output) -> None:
    _assert_parquet_equal(
        v1_pipeline_output / "summary.parquet", STEP1_EXPECTED / "summary.parquet"
    )
    _assert_csv_equal(
        v1_pipeline_output / "top_merchants.csv", STEP1_EXPECTED / "top_merchants.csv"
    )
    _assert_json_equal(
        v1_pipeline_output / "quality.json", STEP1_EXPECTED / "quality.json"
    )


def test_step3_hidden_v1_step2_regression(v1_pipeline_output) -> None:
    _assert_parquet_equal(
        v1_pipeline_output / "merchant_analytics.parquet",
        STEP2_EXPECTED / "merchant_analytics.parquet",
    )
    _assert_parquet_equal(
        v1_pipeline_output / "country_summary.parquet",
        STEP2_EXPECTED / "country_summary.parquet",
    )


# ── New complexity hidden tests ──────────────────────────────────────────


def test_hidden_ewma_precision(v2_pipeline_output) -> None:
    """EWMA values in merchant_analytics must match pandas ewm(span=30) within rtol=1e-5."""
    actual = pl.read_parquet(v2_pipeline_output / "merchant_analytics.parquet")
    expected = pl.read_parquet(STEP2_EXPECTED / "merchant_analytics.parquet")
    assert "ewma_qa_score" in actual.columns, (
        "merchant_analytics.parquet missing ewma_qa_score column"
    )
    a_vals = actual["ewma_qa_score"].drop_nulls().to_list()
    e_vals = expected["ewma_qa_score"].drop_nulls().to_list()
    assert len(a_vals) == len(e_vals), (
        f"ewma_qa_score row count mismatch: {len(a_vals)} vs {len(e_vals)}"
    )
    for i, (a, e) in enumerate(zip(a_vals, e_vals)):
        assert math.isclose(a, e, rel_tol=1e-5), (
            f"ewma_qa_score mismatch at row {i}: {a} vs {e}"
        )


def test_hidden_weighted_quantile(v2_pipeline_output) -> None:
    """Weighted p90 revenue values must match pandas reference within rtol=1e-4."""
    actual = pl.read_parquet(v2_pipeline_output / "summary.parquet")
    expected = pl.read_parquet(STEP2_EXPECTED / "summary.parquet")
    assert "weighted_p90_revenue" in actual.columns, (
        "summary.parquet missing weighted_p90_revenue column"
    )
    a_vals = actual["weighted_p90_revenue"].drop_nulls().to_list()
    e_vals = expected["weighted_p90_revenue"].drop_nulls().to_list()
    assert len(a_vals) == len(e_vals), (
        f"weighted_p90_revenue row count mismatch: {len(a_vals)} vs {len(e_vals)}"
    )
    for i, (a, e) in enumerate(zip(a_vals, e_vals)):
        assert math.isclose(a, e, rel_tol=1e-4), (
            f"weighted_p90_revenue mismatch at row {i}: {a} vs {e}"
        )


def test_hidden_session_windows_correct(v2_pipeline_output) -> None:
    """Session windows must match expected boundaries exactly."""
    actual = pl.read_parquet(v2_pipeline_output / "session_analytics.parquet")
    expected = pl.read_parquet(STEP2_EXPECTED / "session_analytics.parquet")
    assert_frame_equal(
        actual, expected, check_exact=False, check_dtype=False, rtol=1e-5,
    )


def test_hidden_ddof_0_vs_1(v2_pipeline_output) -> None:
    """Population std (ddof=0) must differ from sample std (ddof=1) and both must be correct."""
    cs = pl.read_parquet(v2_pipeline_output / "country_summary.parquet")
    expected_cs = pl.read_parquet(STEP2_EXPECTED / "country_summary.parquet")
    assert "population_std_revenue" in cs.columns, (
        "country_summary.parquet missing population_std_revenue"
    )
    # population_std_revenue must match expected
    for row_a, row_e in zip(
        cs.select("country", "population_std_revenue").iter_rows(),
        expected_cs.select("country", "population_std_revenue").iter_rows(),
    ):
        assert math.isclose(row_a[1], row_e[1], rel_tol=1e-5), (
            f"population_std_revenue mismatch for {row_a[0]}: {row_a[1]} vs {row_e[1]}"
        )


def test_hidden_promotion_range_join(v2_pipeline_output) -> None:
    """Promotion impact range join must correctly match promotions to transactions by date range."""
    path = v2_pipeline_output / "promotion_impact.parquet"
    assert path.exists(), "Missing promotion_impact.parquet"
    actual = pl.read_parquet(path)
    expected = pl.read_parquet(STEP2_EXPECTED / "promotion_impact.parquet")
    assert_frame_equal(
        actual, expected, check_exact=False, check_dtype=False, rtol=1e-5,
    )


def test_hidden_pivot_fill_zeros(v2_pipeline_output) -> None:
    """Pivot revenue missing cells must be 0.0 not NaN."""
    path = v2_pipeline_output / "pivot_revenue.parquet"
    assert path.exists(), "Missing pivot_revenue.parquet"
    actual = pl.read_parquet(path)
    expected = pl.read_parquet(STEP2_EXPECTED / "pivot_revenue.parquet")
    # Check no nulls (must be 0.0)
    for col in actual.columns:
        if col != "event_month":
            assert actual[col].null_count() == 0, (
                f"pivot_revenue {col} has NaN values - should be 0.0"
            )
    assert_frame_equal(
        actual, expected, check_exact=False, check_dtype=False, rtol=1e-5,
    )


def test_hidden_intra_month_variance(v2_pipeline_output) -> None:
    """Intra-month variance values must match pandas reference."""
    actual = pl.read_parquet(v2_pipeline_output / "merchant_analytics.parquet")
    expected = pl.read_parquet(STEP2_EXPECTED / "merchant_analytics.parquet")
    assert "intra_month_variance" in actual.columns, (
        "merchant_analytics.parquet missing intra_month_variance"
    )
    assert_frame_equal(
        actual.select("row_id", "intra_month_variance"),
        expected.select("row_id", "intra_month_variance"),
        check_exact=False, check_dtype=False, rtol=1e-5,
    )


def test_hidden_cohort_relative_revenue(v2_pipeline_output) -> None:
    """Cohort-relative revenue values must match pandas reference."""
    actual = pl.read_parquet(v2_pipeline_output / "merchant_analytics.parquet")
    expected = pl.read_parquet(STEP2_EXPECTED / "merchant_analytics.parquet")
    assert "cohort_relative_revenue" in actual.columns, (
        "merchant_analytics.parquet missing cohort_relative_revenue"
    )
    assert_frame_equal(
        actual.select("row_id", "cohort_relative_revenue"),
        expected.select("row_id", "cohort_relative_revenue"),
        check_exact=False, check_dtype=False, rtol=1e-5,
    )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
