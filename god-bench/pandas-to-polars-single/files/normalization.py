"""Candidate kernel: lazy v2 normalization and prioritized quarantine."""

from __future__ import annotations

import polars as pl


NORMALIZED_COLUMNS = [
    "row_id", "merchant_id", "country", "tier", "segment", "event_date",
    "event_month", "revenue", "cost", "currency", "channel", "question",
    "context", "title", "answer",
]


def normalize_and_quarantine(
    source: pl.LazyFrame, merchants: pl.LazyFrame
) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    """Return contract-sorted normalized valid rows and original invalid rows.

    This starter deliberately mishandles blank keys, error precedence, inactive
    merchants, local-time offsets, and optional null text. Repair it without
    collecting either LazyFrame.
    """
    source_columns = source.collect_schema().names()
    parsed = source.with_columns(
        pl.col("event_ts")
        .str.to_datetime(format="%+", strict=False, time_zone="UTC")
        .alias("_event_date")
    )
    joined = parsed.join(merchants, on="merchant_code", how="left")

    # BUG: these checks are neither complete nor in the required priority order.
    error = (
        pl.when((pl.col("revenue_cents") < 0) | (pl.col("cost_cents") < 0))
        .then(pl.lit("NEGATIVE_AMOUNT"))
        .when(pl.col("merchant_code").is_null() | pl.col("country").is_null())
        .then(pl.lit("NULL_REQUIRED"))
        .when(pl.col("_event_date").is_null())
        .then(pl.lit("INVALID_DATE"))
        .when(pl.col("merchant_id").is_null())
        .then(pl.lit("MISSING_MERCHANT"))
        .otherwise(None)
        .alias("_error")
    )
    classified = joined.with_columns(error)

    quarantine = (
        classified.filter(pl.col("_error").is_not_null())
        .select([pl.col(name) for name in source_columns] + [pl.col("_error").alias("error_code")])
        .sort("row_id")
    )
    valid = (
        classified.filter(pl.col("_error").is_null())
        .with_columns(
            pl.col("_event_date").alias("event_date"),
            pl.col("_event_date").dt.strftime("%Y-%m").alias("event_month"),
            (pl.col("revenue_cents") / 100.0).cast(pl.Float64).alias("revenue"),
            (pl.col("cost_cents") / 100.0).cast(pl.Float64).alias("cost"),
        )
        .select(NORMALIZED_COLUMNS)
        .sort(["merchant_id", "event_date", "row_id"])
    )
    return valid, quarantine
