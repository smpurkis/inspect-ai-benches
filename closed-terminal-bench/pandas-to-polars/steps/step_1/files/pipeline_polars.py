"""Starter scaffold for the pandas-to-polars benchmark pipeline.

Implement the TODO builders with Polars logic while preserving the CLI and output
contracts. Keep the pipeline fully in Polars; do not use pandas intermediates or
``to_pandas()``.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import polars as pl


SchemaVersion = Literal["v1", "v2"]


@dataclass
class PipelineResult:
    """Container for all benchmark outputs.

    Step 1 fills the first three fields. Step 2 extends the same structure with the
    analytics outputs. Step 3 reuses it again for the v2-only artifacts.
    """

    summary: Any = None
    top_merchants: Any = None
    quality: dict[str, Any] | None = None
    merchant_analytics: Any = None
    country_summary: Any = None
    enriched_transactions: Any = None
    quarantine: Any = None
    quality_v2: dict[str, Any] | None = None


def parse_args() -> argparse.Namespace:
    """Parse the benchmark CLI arguments."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_dir", required=True)
    parser.add_argument("--out", dest="out_dir", required=True)
    return parser.parse_args()


def ensure_output_dir(path: str | Path) -> Path:
    """Create the output directory if needed and return it."""

    output_dir = Path(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def detect_schema_version(in_dir: Path) -> SchemaVersion:
    """Detect whether the input directory uses the v1 or v2 layout."""

    if (in_dir / "input_v2.parquet").exists():
        return "v2"
    if (in_dir / "input.parquet").exists():
        return "v1"
    raise FileNotFoundError(
        "Expected either input.parquet (v1) or input_v2.parquet (v2) in --in"
    )


def scan_v1_input(in_dir: Path) -> pl.LazyFrame:
    """Open the step 1/2 input dataset as a lazy Polars frame."""

    return pl.scan_parquet(str(in_dir / "input.parquet"))


def scan_v2_input(in_dir: Path) -> pl.LazyFrame:
    """Open the step 3 schema-evolved input dataset as a lazy Polars frame."""

    return pl.scan_parquet(str(in_dir / "input_v2.parquet"))


def scan_reference_tables(in_dir: Path) -> dict[str, pl.LazyFrame]:
    """Open any available reference tables for the v2 path."""

    reference_tables: dict[str, pl.LazyFrame] = {}
    for name in ("merchants", "categories"):
        path = in_dir / f"{name}.parquet"
        if path.exists():
            reference_tables[name] = pl.scan_parquet(str(path))
    return reference_tables


def collect_frame(frame: Any) -> pl.DataFrame:
    """Materialize a Polars frame only at the write boundary."""

    if isinstance(frame, pl.LazyFrame):
        return frame.collect()
    return frame


def write_parquet_output(frame: Any, output_path: Path) -> None:
    """Write a Parquet artifact from a DataFrame or LazyFrame."""

    collect_frame(frame).write_parquet(output_path)


def write_csv_output(frame: Any, output_path: Path) -> None:
    """Write a CSV artifact from a DataFrame or LazyFrame."""

    collect_frame(frame).write_csv(output_path)


def write_json_output(payload: dict[str, Any], output_path: Path) -> None:
    """Write a deterministic JSON artifact."""

    output_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def write_pipeline_outputs(result: PipelineResult, out_dir: Path) -> None:
    """Persist every populated artifact using the benchmark filenames."""

    if result.summary is not None:
        write_parquet_output(result.summary, out_dir / "summary.parquet")
    if result.top_merchants is not None:
        write_csv_output(result.top_merchants, out_dir / "top_merchants.csv")
    if result.quality is not None:
        write_json_output(result.quality, out_dir / "quality.json")
    if result.merchant_analytics is not None:
        write_parquet_output(
            result.merchant_analytics,
            out_dir / "merchant_analytics.parquet",
        )
    if result.country_summary is not None:
        write_parquet_output(
            result.country_summary, out_dir / "country_summary.parquet"
        )
    if result.enriched_transactions is not None:
        write_parquet_output(
            result.enriched_transactions,
            out_dir / "enriched_transactions.parquet",
        )
    if result.quarantine is not None:
        write_parquet_output(result.quarantine, out_dir / "quarantine.parquet")
    if result.quality_v2 is not None:
        write_json_output(result.quality_v2, out_dir / "quality_v2.json")


def build_v1_outputs(input_lf: pl.LazyFrame) -> PipelineResult:
    """Build the v1 outputs.

    TODO:
    - Filter to rows where has_answer == 1.
    - Derive the Step 1 fields such as net_revenue, profit_flag, and qa_score.
    - Produce summary.parquet, top_merchants.csv, and quality.json.
    - Extend this same function in Step 2 to also populate merchant_analytics and
      country_summary without breaking the original outputs.
    """

    _ = input_lf
    raise NotImplementedError("Implement the v1 Polars pipeline")


def build_v2_outputs(
    input_lf: pl.LazyFrame,
    reference_tables: dict[str, pl.LazyFrame],
) -> PipelineResult:
    """Build the v2 outputs.

    TODO:
    - Preserve lazy execution and start from scan_v2_input/scan_reference_tables.
    - Validate and quarantine bad rows before emitting enriched outputs.
    - Continue producing the step 1 and step 2 outputs where required.
    - Add enriched_transactions.parquet, quarantine.parquet, and quality_v2.json.
    """

    _ = input_lf, reference_tables
    raise NotImplementedError("Implement the v2 Polars pipeline")


def run_v1_pipeline(in_dir: Path, out_dir: Path) -> None:
    """Orchestrate the v1 path and write its outputs."""

    result = build_v1_outputs(scan_v1_input(in_dir))
    write_pipeline_outputs(result, out_dir)


def run_v2_pipeline(in_dir: Path, out_dir: Path) -> None:
    """Orchestrate the v2 path and write its outputs."""

    result = build_v2_outputs(
        scan_v2_input(in_dir),
        scan_reference_tables(in_dir),
    )
    write_pipeline_outputs(result, out_dir)


def main() -> None:
    """Dispatch to the version-specific pipeline while preserving the CLI."""

    args = parse_args()
    in_dir = Path(args.in_dir)
    out_dir = ensure_output_dir(args.out_dir)

    if detect_schema_version(in_dir) == "v2":
        run_v2_pipeline(in_dir, out_dir)
        return

    run_v1_pipeline(in_dir, out_dir)


if __name__ == "__main__":
    main()
