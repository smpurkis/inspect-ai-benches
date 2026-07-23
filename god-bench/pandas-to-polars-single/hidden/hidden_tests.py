#!/usr/bin/env python3

import ast
import hashlib
import json
import math
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
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
METAMORPHIC_ROOT = Path("/tmp/pandas_to_polars_reversed_hidden")
STAGED_ROOT = Path("/tmp/pandas_to_polars_inputs_hidden")
GENERATED_ROOT = Path("/tmp/pandas_to_polars_generated_hidden")
EAGER_OUT_DIR = Path("/tmp/pandas_to_polars_step3_v2_eager_hidden")

REFERENCE_NAMES = ("merchants.parquet", "categories.parquet", "promotions.parquet")
PARQUET_OUTPUTS = (
    "summary.parquet",
    "merchant_analytics.parquet",
    "country_summary.parquet",
    "session_analytics.parquet",
    "promotion_impact.parquet",
    "pivot_revenue.parquet",
    "enriched_transactions.parquet",
    "quarantine.parquet",
)
JSON_OUTPUTS = ("quality.json", "quality_v2.json")
ALL_OUTPUTS = PARQUET_OUTPUTS + ("top_merchants.csv",) + JSON_OUTPUTS
V1_OUTPUTS = (
    "summary.parquet",
    "merchant_analytics.parquet",
    "country_summary.parquet",
    "session_analytics.parquet",
    "promotion_impact.parquet",
    "pivot_revenue.parquet",
    "top_merchants.csv",
    "quality.json",
)
SORT_KEYS = {
    "summary.parquet": ["event_month", "country", "tier", "context_bucket"],
    "merchant_analytics.parquet": ["merchant_id", "event_date", "row_id"],
    "country_summary.parquet": ["country"],
    "session_analytics.parquet": ["merchant_id", "session_id"],
    "promotion_impact.parquet": ["merchant_id", "event_date", "row_id", "promo_id"],
    "pivot_revenue.parquet": ["event_month"],
    "enriched_transactions.parquet": ["merchant_id", "event_date", "row_id"],
    "quarantine.parquet": ["row_id"],
}

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


def _fixture_hashes() -> dict[Path, str]:
    roots = (HIDDEN_V2_DATA, STEP1_FILES / "public_data")
    return {
        path: _sha256(path)
        for root in roots
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _assert_parquet_equal(actual: Path, expected: Path, atol: float = 5e-7) -> None:
    assert actual.is_file(), f"missing output: {actual.name}"
    df_a = pl.read_parquet(actual)
    df_e = pl.read_parquet(expected)
    assert df_a.columns == df_e.columns, f"{actual.name}: column order differs"
    assert df_a.schema == df_e.schema, f"{actual.name}: dtypes differ"
    assert_frame_equal(
        df_a,
        df_e,
        check_exact=False,
        check_dtypes=True,
        rel_tol=0.0,
        abs_tol=atol,
    )

    sort_keys = SORT_KEYS.get(actual.name)
    if sort_keys:
        assert_frame_equal(df_a, df_a.sort(sort_keys), check_exact=True)

    for column, dtype in df_a.schema.items():
        if "Datetime" in str(dtype):
            assert "UTC" in str(dtype), f"{actual.name}.{column} is not UTC: {dtype}"
        if dtype in (pl.Float32, pl.Float64):
            for value in df_a[column].drop_nulls().to_list():
                assert math.isfinite(value), f"{actual.name}.{column} is non-finite"
                assert value == round(value, 6), (
                    f"{actual.name}.{column} contains an unrounded value: {value}"
                )


def _assert_csv_equal(actual: Path, expected: Path) -> None:
    assert actual.is_file(), f"missing output: {actual.name}"
    df_a = pl.read_csv(actual)
    df_e = pl.read_csv(expected)
    assert df_a.columns == df_e.columns, f"{actual.name}: column order differs"
    assert df_a.schema == df_e.schema, f"{actual.name}: inferred dtypes differ"
    assert_frame_equal(
        df_a, df_e, check_exact=False, check_dtypes=True, rel_tol=0.0, abs_tol=5e-7
    )
    assert_frame_equal(
        df_a,
        df_a.sort(["country", "merchant_revenue", "merchant_id"], descending=[False, True, False]),
        check_exact=True,
    )
    for column, dtype in df_a.schema.items():
        if dtype in (pl.Float32, pl.Float64):
            assert all(value == round(value, 6) for value in df_a[column].drop_nulls())


def _assert_json_equal(actual: Path, expected: Path) -> None:
    assert actual.is_file(), f"missing output: {actual.name}"
    a = json.loads(actual.read_text(encoding="utf-8"))
    e = json.loads(expected.read_text(encoding="utf-8"))
    assert a == e
    compact = json.dumps(a, sort_keys=True, separators=(",", ":"))
    assert actual.read_text(encoding="utf-8").rstrip("\n") == compact


def _assert_output_set(actual_dir: Path, expected_dir: Path) -> None:
    actual_names = {path.name for path in actual_dir.iterdir() if path.is_file()}
    assert actual_names == set(ALL_OUTPUTS)
    for name in PARQUET_OUTPUTS:
        _assert_parquet_equal(actual_dir / name, expected_dir / name)
    _assert_csv_equal(
        actual_dir / "top_merchants.csv", expected_dir / "top_merchants.csv"
    )
    for name in JSON_OUTPUTS:
        _assert_json_equal(actual_dir / name, expected_dir / name)


def _assert_output_dirs_equal(actual_dir: Path, expected_dir: Path) -> None:
    for name in PARQUET_OUTPUTS:
        _assert_parquet_equal(actual_dir / name, expected_dir / name)
    _assert_csv_equal(
        actual_dir / "top_merchants.csv", expected_dir / "top_merchants.csv"
    )
    for name in JSON_OUTPUTS:
        _assert_json_equal(actual_dir / name, expected_dir / name)


def _stage_input(source_dir: Path, marker: str, destination: Path) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    shutil.copy2(source_dir / marker, destination / marker)
    for name in REFERENCE_NAMES:
        source = source_dir / name
        if source.exists():
            shutil.copy2(source, destination / name)
    assert not (destination / "expected").exists()
    return destination


def _run_candidate(input_dir: Path, output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    subprocess.check_call(
        [sys.executable, str(CANDIDATE), "--in", str(input_dir), "--out", str(output_dir)],
        timeout=120,
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

    wrapper_path = Path("/tmp/_lazy_enforcer_step3_hidden.py")
    wrapper_path.write_text(wrapper)

    subprocess.check_call(
        [sys.executable, str(wrapper_path)],
        timeout=120,
    )


def _build_v1_input(destination: Path) -> Path:
    """Convert hidden v2 valid rows into a v1-only input without exposing outputs."""
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    source = pl.read_parquet(HIDDEN_V2_DATA / "input_v2.parquet")
    quarantined_ids = pl.read_parquet(
        STEP3_EXPECTED / "quarantine.parquet", columns=["row_id"]
    )
    merchants = pl.read_parquet(HIDDEN_V2_DATA / "merchants.parquet")
    valid = source.join(quarantined_ids, on="row_id", how="anti").join(
        merchants.select("merchant_code", "merchant_id", "tier"),
        on="merchant_code",
        how="left",
    )
    v1 = valid.with_columns(
        pl.col("event_ts")
        .str.to_datetime(strict=False, time_unit="us", time_zone="UTC")
        .alias("event_date"),
        (pl.col("revenue_cents") / 100.0).cast(pl.Float64).alias("revenue"),
        (pl.col("cost_cents") / 100.0).cast(pl.Float64).alias("cost"),
    ).with_columns(pl.col("event_date").dt.strftime("%Y-%m").alias("event_month"))
    v1.select(
        "row_id",
        "doc_id",
        "question_id",
        "qa_id",
        "question",
        "context",
        "title",
        "answer",
        "merchant_id",
        "country",
        "event_date",
        "event_month",
        "revenue",
        "cost",
        "tier",
    ).write_parquet(destination / "input.parquet")
    shutil.copy2(HIDDEN_V2_DATA / "promotions.parquet", destination / "promotions.parquet")
    assert {path.name for path in destination.iterdir()} == {
        "input.parquet",
        "promotions.parquet",
    }
    return destination


def _clone_row(template: pl.DataFrame, **values) -> pl.DataFrame:
    schema = template.schema
    return template.with_columns(
        [pl.lit(value).cast(schema[name]).alias(name) for name, value in values.items()]
    )


def _build_generated_v2_input(destination: Path) -> Path:
    """Create deterministic schema, quarantine, DST, join, and window edge cases."""
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    source = pl.read_parquet(HIDDEN_V2_DATA / "input_v2.parquet")
    merchants = pl.read_parquet(HIDDEN_V2_DATA / "merchants.parquet")
    active = merchants.filter(pl.col("is_active")).sort("merchant_id").head(2)
    inactive = merchants.filter(~pl.col("is_active")).sort("merchant_id").head(1)
    assert active.height == 2 and inactive.height == 1
    active_rows = active.select("merchant_code", "merchant_id").rows()
    inactive_code = inactive["merchant_code"][0]
    merchant_code, merchant_id = active_rows[0]
    second_code, _ = active_rows[1]

    template = source.head(1)
    common = {
        "doc_id": 700001,
        "question_id": 700002,
        "qa_id": 700003,
        "question": "which result",
        "context": "one two three",
        "title": "edge",
        "answer": "yes",
        "country": "US",
        "currency": "USD",
        "channel": "generated",
        "cost_cents": 100,
    }

    def row(row_id: int, **values) -> pl.DataFrame:
        return _clone_row(template, **(common | {"row_id": row_id} | values))

    generated = pl.concat(
        [
            row(
                900001,
                merchant_code=merchant_code,
                event_ts="2024-03-10T01:30:00-05:00",
                revenue_cents=1000,
            ),
            row(
                900002,
                merchant_code=merchant_code,
                event_ts="2024-03-10T03:30:00-04:00",
                revenue_cents=2000,
            ),
            row(
                900003,
                merchant_code=merchant_code,
                event_ts="2024-03-10T03:30:00-04:00",
                revenue_cents=3000,
            ),
            row(
                900004,
                merchant_code=second_code,
                event_ts="2024-11-03T01:30:00-05:00",
                revenue_cents=4000,
                context=None,
                answer=None,
            ),
            row(
                900010,
                merchant_code=None,
                country="",
                event_ts="not-a-date",
                revenue_cents=-1,
            ),
            row(
                900011,
                merchant_code=merchant_code,
                event_ts="2023-12-31T23:00:00+00:00",
                revenue_cents=1000,
            ),
            row(
                900012,
                merchant_code=merchant_code,
                event_ts="2024-06-01T00:00:00+00:00",
                revenue_cents=-1,
            ),
            row(
                900013,
                merchant_code="M-MISSING",
                event_ts="2024-06-01T00:00:00+00:00",
                revenue_cents=1000,
            ),
            row(
                900014,
                merchant_code=inactive_code,
                event_ts="2024-06-01T00:00:00+00:00",
                revenue_cents=1000,
            ),
        ],
        how="vertical",
    )
    generated.write_parquet(destination / "input_v2.parquet")
    shutil.copy2(HIDDEN_V2_DATA / "merchants.parquet", destination / "merchants.parquet")
    shutil.copy2(HIDDEN_V2_DATA / "categories.parquet", destination / "categories.parquet")

    promo_template = pl.read_parquet(HIDDEN_V2_DATA / "promotions.parquet").head(1)
    start = datetime(2024, 3, 10, 0, 0, tzinfo=timezone.utc)
    end = datetime(2024, 3, 11, 0, 0, tzinfo=timezone.utc)
    promotions = pl.concat(
        [
            _clone_row(
                promo_template,
                promo_id=9901,
                merchant_id=merchant_id,
                promo_start=start,
                promo_end=end,
                discount_pct=10.0,
            ),
            _clone_row(
                promo_template,
                promo_id=9902,
                merchant_id=merchant_id,
                promo_start=start,
                promo_end=end,
                discount_pct=20.0,
            ),
        ],
        how="vertical",
    )
    promotions.write_parquet(destination / "promotions.parquet")
    return destination


@pytest.fixture(scope="module", autouse=True)
def immutable_fixture_hashes():
    known = {
        HIDDEN_V2_DATA / "input_v2.parquet": "9f40ccccbdbcb46d1c6963cd7e01baa0f29f085093bc9f9be81a4295df7e3824",
        STEP3_EXPECTED / "enriched_transactions.parquet": HIDDEN_EXPECTED_ENRICHED_SHA256,
        STEP3_EXPECTED / "quarantine.parquet": HIDDEN_EXPECTED_QUARANTINE_SHA256,
        STEP3_EXPECTED / "quality_v2.json": HIDDEN_EXPECTED_QUALITY_V2_SHA256,
    }
    for path, digest in known.items():
        assert _sha256(path) == digest, f"fixture hash mismatch before tests: {path}"
    before = _fixture_hashes()
    yield
    after = _fixture_hashes()
    assert after == before, "candidate modified public or hidden fixture data"


@pytest.fixture(scope="module")
def v2_pipeline_output():
    """Run the candidate pipeline with v2 hidden data under lazy enforcement."""
    assert CANDIDATE.exists(), "Missing /app/files/pipeline_polars.py"
    input_dir = _stage_input(
        HIDDEN_V2_DATA, "input_v2.parquet", STAGED_ROOT / "v2"
    )
    _run_candidate_with_lazy_enforcement(input_dir, OUT_DIR_V2)
    return OUT_DIR_V2


@pytest.fixture(scope="module")
def v1_pipeline_output():
    """Run the candidate pipeline with v1 hidden data under lazy enforcement."""
    assert CANDIDATE.exists(), "Missing /app/files/pipeline_polars.py"
    input_dir = _build_v1_input(STAGED_ROOT / "v1")
    _run_candidate_with_lazy_enforcement(input_dir, OUT_DIR_V1)
    return OUT_DIR_V1


@pytest.fixture(scope="module")
def reversed_v2_pipeline_output(v2_pipeline_output):
    """Run a deterministic generated case with reversed source-row order."""
    if METAMORPHIC_ROOT.exists():
        shutil.rmtree(METAMORPHIC_ROOT)
    input_dir = METAMORPHIC_ROOT / "input"
    output_dir = METAMORPHIC_ROOT / "output"
    input_dir.mkdir(parents=True)

    source = pl.read_parquet(HIDDEN_V2_DATA / "input_v2.parquet")
    source.reverse().write_parquet(input_dir / "input_v2.parquet")
    for name in ("merchants.parquet", "categories.parquet", "promotions.parquet"):
        shutil.copy2(HIDDEN_V2_DATA / name, input_dir / name)

    _run_candidate_with_lazy_enforcement(input_dir, output_dir)
    return output_dir


@pytest.fixture(scope="module")
def eager_v2_pipeline_output(v2_pipeline_output):
    input_dir = STAGED_ROOT / "v2"
    _run_candidate(input_dir, EAGER_OUT_DIR)
    return EAGER_OUT_DIR


@pytest.fixture(scope="module")
def generated_v2_pipeline_output():
    input_dir = _build_generated_v2_input(GENERATED_ROOT / "input")
    output_dir = GENERATED_ROOT / "output"
    _run_candidate_with_lazy_enforcement(input_dir, output_dir)
    return input_dir, output_dir


# ── Tests ─────────────────────────────────────────────────────────────────


def test_hidden_candidate_does_not_delegate_to_eager_or_reference_pipelines() -> None:
    source = CANDIDATE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = {
        "pandas",
        "pipeline_pandas",
        "pipeline_pandas_advanced",
        "pipeline_pandas_v2",
        "importlib",
        "runpy",
        "subprocess",
    }
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"__import__", "compile", "eval", "exec"}, (
                f"forbidden dynamic delegation call: {node.func.id}"
            )
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {
                "exec_module",
                "popen",
                "read_csv",
                "read_parquet",
                "run",
                "system",
                "to_pandas",
            }, (
                f"forbidden eager/delegating call: {node.func.attr}"
            )
    assert not imported & forbidden_modules, (
        f"forbidden delegation imports: {sorted(imported & forbidden_modules)}"
    )
    string_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not any("pipeline_pandas" in value for value in string_literals), (
        "candidate references an executable reference pipeline"
    )


def test_hidden_candidate_received_input_only(v2_pipeline_output) -> None:
    staged = STAGED_ROOT / "v2"
    assert {path.name for path in staged.iterdir()} == {
        "input_v2.parquet",
        *REFERENCE_NAMES,
    }
    assert not (staged / "expected").exists()


def test_hidden_all_v2_artifacts_match_full_contract(v2_pipeline_output) -> None:
    _assert_output_set(v2_pipeline_output, STEP3_EXPECTED)


def test_hidden_all_v1_artifacts_match_full_contract(v1_pipeline_output) -> None:
    actual_names = {path.name for path in v1_pipeline_output.iterdir() if path.is_file()}
    assert actual_names == set(V1_OUTPUTS)
    for name in V1_OUTPUTS:
        actual = v1_pipeline_output / name
        expected = STEP3_EXPECTED / name
        if name.endswith(".parquet"):
            _assert_parquet_equal(actual, expected)
        elif name.endswith(".csv"):
            _assert_csv_equal(actual, expected)
        else:
            _assert_json_equal(actual, expected)


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
        actual, expected, check_exact=False, check_dtypes=True, rel_tol=1e-5,
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
        actual, expected, check_exact=False, check_dtypes=True, rel_tol=1e-5,
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
        actual, expected, check_exact=False, check_dtypes=True, rel_tol=1e-5,
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
        check_exact=False, check_dtypes=True, rel_tol=1e-5,
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
        check_exact=False, check_dtypes=True, rel_tol=1e-5,
    )


def test_hidden_source_order_invariance(
    v2_pipeline_output, reversed_v2_pipeline_output
) -> None:
    """All contract-sorted outputs must ignore physical input row order."""
    parquet_names = (
        "summary.parquet",
        "merchant_analytics.parquet",
        "country_summary.parquet",
        "session_analytics.parquet",
        "promotion_impact.parquet",
        "pivot_revenue.parquet",
        "enriched_transactions.parquet",
        "quarantine.parquet",
    )
    for name in parquet_names:
        _assert_parquet_equal(
            reversed_v2_pipeline_output / name,
            v2_pipeline_output / name,
        )
    _assert_csv_equal(
        reversed_v2_pipeline_output / "top_merchants.csv",
        v2_pipeline_output / "top_merchants.csv",
    )
    for name in ("quality.json", "quality_v2.json"):
        _assert_json_equal(
            reversed_v2_pipeline_output / name,
            v2_pipeline_output / name,
        )


def test_hidden_lazy_and_unrestricted_execution_are_equivalent(
    v2_pipeline_output, eager_v2_pipeline_output
) -> None:
    """Monkey-patched lazy execution must not alter any emitted artifact."""
    _assert_output_dirs_equal(eager_v2_pipeline_output, v2_pipeline_output)


def test_hidden_generated_schema_versions_use_distinct_columns(
    v1_pipeline_output, generated_v2_pipeline_output
) -> None:
    v1_schema = pl.read_parquet_schema(STAGED_ROOT / "v1" / "input.parquet")
    v2_input, _ = generated_v2_pipeline_output
    v2_schema = pl.read_parquet_schema(v2_input / "input_v2.parquet")
    assert {"merchant_id", "event_date", "revenue", "cost", "tier"} <= set(v1_schema)
    assert not {"merchant_code", "event_ts", "revenue_cents", "cost_cents"} & set(v1_schema)
    assert {"merchant_code", "event_ts", "revenue_cents", "cost_cents"} <= set(v2_schema)
    assert not {"merchant_id", "event_date", "revenue", "cost", "tier", "event_month"} & set(v2_schema)


def test_hidden_generated_quarantine_priority_and_nulls(
    generated_v2_pipeline_output,
) -> None:
    _, output_dir = generated_v2_pipeline_output
    quarantine = pl.read_parquet(output_dir / "quarantine.parquet")
    assert quarantine.select("row_id", "error_code").rows() == [
        (900010, "NULL_REQUIRED"),
        (900011, "INVALID_DATE"),
        (900012, "NEGATIVE_AMOUNT"),
        (900013, "MISSING_MERCHANT"),
        (900014, "INACTIVE_MERCHANT"),
    ]
    quality = json.loads((output_dir / "quality_v2.json").read_text(encoding="utf-8"))
    assert quality["total_input_rows"] == 9
    assert quality["valid_rows"] == 4
    assert quality["quarantined_rows"] == 5
    assert quality["row_count"] == 3
    assert quality["quarantine_by_error"] == {
        "INACTIVE_MERCHANT": 1,
        "INVALID_DATE": 1,
        "MISSING_MERCHANT": 1,
        "NEGATIVE_AMOUNT": 1,
        "NULL_REQUIRED": 1,
    }


def test_hidden_generated_dst_joins_windows_and_duplicate_order(
    generated_v2_pipeline_output,
) -> None:
    _, output_dir = generated_v2_pipeline_output
    enriched = pl.read_parquet(output_dir / "enriched_transactions.parquet")
    assert enriched["row_id"].to_list() == [900001, 900002, 900003]
    assert "UTC" in str(enriched.schema["event_date"])
    assert enriched["event_date"].dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_list() == [
        "2024-03-10T06:30:00Z",
        "2024-03-10T07:30:00Z",
        "2024-03-10T07:30:00Z",
    ]
    assert enriched["rolling_30d_revenue"].to_list() == [10.0, 30.0, 60.0]
    assert enriched["monthly_cumulative_revenue"].to_list() == [10.0, 30.0, 60.0]
    for column in ("segment", "category_label", "priority", "sla_hours"):
        assert enriched[column].null_count() == 0, f"generated join missed {column}"

    impact = pl.read_parquet(output_dir / "promotion_impact.parquet")
    assert impact.select("row_id", "promo_id").rows() == [
        (900001, 9901),
        (900001, 9902),
        (900002, 9901),
        (900002, 9902),
        (900003, 9901),
        (900003, 9902),
    ]


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
