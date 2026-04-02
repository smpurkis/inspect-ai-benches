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
    "be0015b32b1daf1f10012c22de229370e9195c52bdae76bf973eaaf2ae0bec7c"
)
PUBLIC_EXPECTED_QUARANTINE_SHA256 = (
    "8a4c46e5515697c13a4403aab2ccdc87a49252c77f8dc608da178ea95b66eea5"
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


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
