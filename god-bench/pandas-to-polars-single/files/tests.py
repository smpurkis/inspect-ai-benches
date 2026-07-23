#!/usr/bin/env python3

import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import polars as pl
import pytest


BASE = Path(__file__).resolve().parent
CANDIDATE = BASE / "pipeline_polars.py"
PUBLIC_DATA = BASE / "public_data"
EXPECTED = PUBLIC_DATA / "expected"
STAGED_ROOT = Path("/tmp/pandas_to_polars_public_inputs")
OUT_DIR_V1 = Path("/tmp/pandas_to_polars_public_v1")
OUT_DIR_V2 = Path("/tmp/pandas_to_polars_public_v2")
LAZY_OUT_DIR = Path("/tmp/pandas_to_polars_public_lazy")

V1_OUTPUTS = {
    "summary.parquet",
    "top_merchants.csv",
    "quality.json",
    "merchant_analytics.parquet",
    "country_summary.parquet",
    "session_analytics.parquet",
    "promotion_impact.parquet",
    "pivot_revenue.parquet",
}
V2_OUTPUTS = V1_OUTPUTS | {
    "enriched_transactions.parquet",
    "quarantine.parquet",
    "quality_v2.json",
}


def _stage_input(version: str) -> Path:
    destination = STAGED_ROOT / version
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    marker = "input.parquet" if version == "v1" else "input_v2.parquet"
    shutil.copy2(PUBLIC_DATA / marker, destination / marker)
    references = ("promotions.parquet",) if version == "v1" else (
        "merchants.parquet",
        "categories.parquet",
        "promotions.parquet",
    )
    for name in references:
        shutil.copy2(PUBLIC_DATA / name, destination / name)
    return destination


def _reset_output(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)


def _run_candidate(input_dir: Path, output_dir: Path) -> None:
    _reset_output(output_dir)
    subprocess.check_call(
        [sys.executable, str(CANDIDATE), "--in", str(input_dir), "--out", str(output_dir)],
        timeout=120,
    )


def _run_with_eager_reads_blocked(input_dir: Path, output_dir: Path) -> None:
    _reset_output(output_dir)
    wrapper = textwrap.dedent(f"""\
        import sys
        import polars as pl

        def blocked(*args, **kwargs):
            raise RuntimeError("Use scan_parquet/scan_csv for lazy input")

        pl.read_parquet = blocked
        pl.read_csv = blocked
        sys.argv = [
            "pipeline_polars.py", "--in", {str(input_dir)!r},
            "--out", {str(output_dir)!r},
        ]
        sys.path.insert(0, {str(BASE)!r})
        import pipeline_polars
        pipeline_polars.main()
    """)
    subprocess.run(
        [sys.executable, "-c", wrapper],
        check=True,
        timeout=120,
    )


@pytest.fixture(scope="module")
def v1_output() -> Path:
    output_dir = OUT_DIR_V1
    _run_candidate(_stage_input("v1"), output_dir)
    return output_dir


@pytest.fixture(scope="module")
def v2_output() -> Path:
    output_dir = OUT_DIR_V2
    _run_candidate(_stage_input("v2"), output_dir)
    return output_dir


def _names(output_dir: Path) -> set[str]:
    return {path.name for path in output_dir.iterdir() if path.is_file()}


def test_entrypoint_exposes_in_and_out_cli() -> None:
    assert CANDIDATE.is_file(), "Missing /app/files/pipeline_polars.py"
    result = subprocess.run(
        [sys.executable, str(CANDIDATE), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--in" in result.stdout and "--out" in result.stdout


def test_v1_smoke_emits_contract_artifacts(v1_output: Path) -> None:
    assert _names(v1_output) == V1_OUTPUTS
    assert pl.read_parquet(v1_output / "summary.parquet").height > 0
    assert isinstance(json.loads((v1_output / "quality.json").read_text()), dict)


def test_v2_smoke_emits_contract_artifacts(v2_output: Path) -> None:
    assert _names(v2_output) == V2_OUTPUTS
    assert pl.read_parquet(v2_output / "enriched_transactions.parquet").height > 0
    assert isinstance(json.loads((v2_output / "quality_v2.json").read_text()), dict)


def test_v1_schema_smoke(v1_output: Path) -> None:
    for name in ("summary.parquet", "merchant_analytics.parquet"):
        assert pl.read_parquet_schema(v1_output / name) == pl.read_parquet_schema(EXPECTED / name)


def test_v2_schema_smoke(v2_output: Path) -> None:
    for name in ("enriched_transactions.parquet", "quarantine.parquet"):
        assert pl.read_parquet_schema(v2_output / name) == pl.read_parquet_schema(EXPECTED / name)


def test_lazy_input_api_smoke() -> None:
    _run_with_eager_reads_blocked(_stage_input("v2"), LAZY_OUT_DIR)
    assert V2_OUTPUTS <= _names(LAZY_OUT_DIR)


if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
