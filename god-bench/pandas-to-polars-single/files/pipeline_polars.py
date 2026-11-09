"""Trusted CLI and downstream analytics for the compact normalization task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

from normalization import normalize_and_quarantine


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="input_dir", required=True)
    parser.add_argument("--out", dest="output_dir", required=True)
    return parser.parse_args()


def _analytics(valid: pl.DataFrame, quarantine: pl.DataFrame) -> dict:
    errors = {
        code: count
        for code, count in quarantine.group_by("error_code").len().sort("error_code").rows()
    }
    countries = {
        country: round(revenue, 6)
        for country, revenue in (
            valid.group_by("country")
            .agg(pl.col("revenue").sum().alias("revenue"))
            .sort("country")
            .rows()
        )
    }
    return {
        "quarantine_by_error": errors,
        "quarantined_rows": quarantine.height,
        "revenue_by_country": countries,
        "total_input_rows": valid.height + quarantine.height,
        "valid_rows": valid.height,
    }


def run(input_dir: Path, output_dir: Path) -> None:
    source = pl.scan_parquet(input_dir / "input_v2.parquet")
    merchants = pl.scan_parquet(input_dir / "merchants.parquet")
    valid_lf, quarantine_lf = normalize_and_quarantine(source, merchants)
    valid = valid_lf.collect()
    quarantine = quarantine_lf.collect()
    output_dir.mkdir(parents=True, exist_ok=True)
    valid.write_parquet(output_dir / "normalized.parquet")
    quarantine.write_parquet(output_dir / "quarantine.parquet")
    (output_dir / "analytics.json").write_text(
        json.dumps(_analytics(valid, quarantine), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def main() -> None:
    args = _arguments()
    run(Path(args.input_dir), Path(args.output_dir))


if __name__ == "__main__":
    main()
