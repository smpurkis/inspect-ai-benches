"""Polars reference implementation for all 3 steps.

Produces:
  Step 1: summary.parquet, top_merchants.csv, quality.json
  Step 2: merchant_analytics.parquet, country_summary.parquet
  Step 3 (v2 mode): enriched_transactions.parquet, quarantine.parquet, quality_v2.json

Uses pl.scan_parquet / pl.scan_csv (lazy) throughout.
"""

import argparse
import json
from pathlib import Path

import polars as pl
import numpy as np


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_dir", required=True)
    p.add_argument("--out", dest="out_dir", required=True)
    return p.parse_args()


# ---------------------------------------------------------------------------
# _ensure_columns  (same logic as the pandas reference)
# ---------------------------------------------------------------------------

def _ensure_columns(df: pl.DataFrame) -> pl.DataFrame:
    # event_date: ensure datetime[us, UTC]
    if "event_date" in df.columns:
        if df.schema["event_date"] != pl.Datetime("us", "UTC"):
            df = df.with_columns(
                pl.col("event_date").cast(pl.Datetime("us", "UTC"))
            )
    else:
        df = df.with_columns(
            pl.lit(pl.Series("event_date", [None], dtype=pl.Datetime("us", "UTC")))
              .cast(pl.Datetime("us", "UTC"))
              .alias("event_date")
        )
        from datetime import datetime, timezone
        df = df.with_columns(
            pl.lit(datetime(2024, 1, 1, tzinfo=timezone.utc)).alias("event_date")
        )

    # Fill nulls for string cols
    for col in ["question", "context", "title", "answer", "country", "tier"]:
        if col in df.columns:
            df = df.with_columns(pl.col(col).fill_null("").cast(pl.Utf8))

    # Cast int columns
    for col in ["doc_id", "question_id", "qa_id"]:
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Int64))

    # Length columns
    df = df.with_columns([
        pl.col("question").str.len_chars().cast(pl.Int64).alias("question_length"),
        pl.col("context").str.len_chars().cast(pl.Int64).alias("context_length"),
        pl.col("answer").str.len_chars().cast(pl.Int64).alias("answer_length"),
        pl.col("title").str.len_chars().cast(pl.Int64).alias("title_length"),
    ])

    # Token count: count non-whitespace sequences
    df = df.with_columns([
        pl.col("question").str.count_matches(r"\S+").fill_null(0).cast(pl.Int64).alias("question_tokens"),
        pl.col("context").str.count_matches(r"\S+").fill_null(0).cast(pl.Int64).alias("context_tokens"),
        pl.col("answer").str.count_matches(r"\S+").fill_null(0).cast(pl.Int64).alias("answer_tokens"),
        pl.col("title").str.count_matches(r"\S+").fill_null(0).cast(pl.Int64).alias("title_tokens"),
    ])

    # Flags
    df = df.with_columns([
        (pl.col("answer_length") > 0).cast(pl.Int8).alias("has_answer"),
        (pl.col("context_tokens") >= 360).cast(pl.Int8).alias("is_long_context"),
    ])

    # Buckets
    df = df.with_columns([
        pl.when(pl.col("context_tokens") < 120).then(pl.lit("short"))
          .when(pl.col("context_tokens") < 360).then(pl.lit("medium"))
          .otherwise(pl.lit("long"))
          .alias("context_bucket"),
        pl.when(pl.col("question_tokens") < 12).then(pl.lit("short"))
          .when(pl.col("question_tokens") < 22).then(pl.lit("medium"))
          .otherwise(pl.lit("long"))
          .alias("question_bucket"),
    ])

    # event_month
    df = df.with_columns(
        pl.col("event_date").dt.strftime("%Y-%m").alias("event_month")
    )

    # margin, margin_pct
    df = df.with_columns([
        (pl.col("revenue") - pl.col("cost")).alias("margin"),
    ])
    df = df.with_columns([
        pl.when(pl.col("revenue") != 0.0)
          .then(pl.col("margin") / pl.col("revenue"))
          .otherwise(0.0)
          .alias("margin_pct"),
    ])

    # net_revenue, profit_flag
    df = df.with_columns([
        (pl.col("revenue") - pl.col("cost")).alias("net_revenue"),
    ])
    df = df.with_columns([
        (pl.col("net_revenue") >= 25).cast(pl.Int8).alias("profit_flag"),
    ])

    # qa_score
    df = df.with_columns([
        (
            (pl.col("question_tokens").cast(pl.Float64) * 1.3
             + pl.col("answer_tokens").cast(pl.Float64) * 2.1)
            / (pl.col("context_tokens").cast(pl.Float64) + 10.0)
        ).cast(pl.Float64).alias("qa_score"),
    ])

    # is_premium
    df = df.with_columns([
        (pl.col("tier") == "premium").cast(pl.Int8).alias("is_premium"),
    ])

    return df


# ---------------------------------------------------------------------------
# Step 1: summary.parquet, top_merchants.csv, quality.json
# ---------------------------------------------------------------------------

def _build_step1_outputs(df: pl.DataFrame, out_dir: Path) -> None:
    filt = df.filter(pl.col("has_answer") == 1)

    # summary.parquet
    summary = (
        filt.group_by(["country", "tier", "event_month", "context_bucket"])
        .agg([
            pl.col("row_id").count().alias("rows"),
            pl.col("revenue").mean().alias("avg_revenue"),
            pl.col("margin_pct").mean().alias("avg_margin_pct"),
            pl.col("qa_score").quantile(0.9, interpolation="linear").alias("p90_qa_score"),
            pl.col("profit_flag").mean().alias("profit_rate"),
        ])
        .sort(["event_month", "country", "tier", "context_bucket"])
    )

    summary = summary.with_columns([
        pl.col("avg_revenue").round(6),
        pl.col("avg_margin_pct").round(6),
        pl.col("p90_qa_score").round(6),
        pl.col("profit_rate").round(6),
    ])

    summary.write_parquet(out_dir / "summary.parquet")

    # top_merchants.csv
    merchants = (
        filt.group_by(["country", "merchant_id"])
        .agg([
            pl.col("row_id").count().alias("merchant_rows"),
            pl.col("revenue").sum().alias("merchant_revenue"),
            pl.col("margin").sum().alias("merchant_margin"),
            pl.col("qa_score").mean().alias("merchant_avg_qa"),
        ])
        .sort(
            ["country", "merchant_revenue", "merchant_margin", "merchant_id"],
            descending=[False, True, True, False],
        )
    )

    # Top 3 per country: use a rank over country ordered by revenue desc, margin desc, merchant_id asc
    # The pandas code does groupby("country").head(3), which takes the first 3 rows per group
    # after the sort above.
    merchants = merchants.with_columns(
        pl.col("merchant_id").cum_count().over("country").alias("_rank")
    )
    top_merchants = (
        merchants.filter(pl.col("_rank") <= 3)
        .select(["country", "merchant_id", "merchant_revenue", "merchant_margin", "merchant_avg_qa"])
        .sort(
            ["country", "merchant_revenue", "merchant_id"],
            descending=[False, True, False],
        )
    )

    top_merchants = top_merchants.with_columns([
        pl.col("merchant_revenue").round(6),
        pl.col("merchant_margin").round(6),
        pl.col("merchant_avg_qa").round(6),
    ])

    # Write CSV with 6 decimal places for floats
    # Use pandas to get exact float format
    top_merchants.to_pandas().to_csv(
        out_dir / "top_merchants.csv", index=False, float_format="%.6f"
    )

    # quality.json
    counts = filt.group_by("country").agg(pl.col("row_id").count().alias("cnt"))
    max_count = counts["cnt"].max()
    top_countries = counts.filter(pl.col("cnt") == max_count)["country"].sort().to_list()
    top_country = top_countries[0]

    max_event = filt["event_date"].max()
    run_id = max_event.strftime("%Y%m%d-000000")

    quality = {
        "row_count": int(len(filt)),
        "distinct_merchants": int(filt["merchant_id"].n_unique()),
        "mean_qa_score": round(float(filt["qa_score"].mean()), 6),
        "pct_premium": round(float(filt["is_premium"].mean()), 6),
        "top_country": top_country,
        "run_id": run_id,
    }

    (out_dir / "quality.json").write_text(
        json.dumps(quality, sort_keys=True, separators=(",", ":")) + "\n"
    )


# ---------------------------------------------------------------------------
# Step 2: merchant_analytics.parquet
# ---------------------------------------------------------------------------

def build_merchant_analytics(df: pl.DataFrame) -> pl.DataFrame:
    df = df.filter(pl.col("has_answer") == 1)
    df = df.sort(["merchant_id", "event_date", "row_id"])

    # 1. Rolling 30-day revenue per merchant
    # Need to convert to pandas for rolling by date, then back
    # Use group_by + map_groups for rolling 30d
    def _rolling_30d(group_df: pl.DataFrame) -> pl.DataFrame:
        # group_df is already sorted by event_date, row_id
        dates = group_df["event_date"].to_list()
        revenues = group_df["revenue"].to_list()
        n = len(dates)
        result = []
        for i in range(n):
            current_date = dates[i]
            total = 0.0
            for j in range(i, -1, -1):
                diff = (current_date - dates[j]).total_seconds()
                if diff < 30 * 86400:  # 30 days in seconds, strictly less (pandas rolling is half-open)
                    total += revenues[j]
                else:
                    break
            result.append(total)
        return group_df.with_columns(
            pl.Series("rolling_30d_revenue", result, dtype=pl.Float64)
        )

    df = df.group_by("merchant_id", maintain_order=True).map_groups(_rolling_30d)
    # Re-sort after map_groups
    df = df.sort(["merchant_id", "event_date", "row_id"])

    # 2. Dense rank of revenue within (country, tier), descending
    df = df.with_columns(
        pl.col("revenue")
          .rank(method="dense", descending=True)
          .over(["country", "tier"])
          .cast(pl.Int64)
          .alias("revenue_rank")
    )

    # 3. QA percentile band within (country, tier)
    # percent_rank (average method) then cut into quartiles
    df = df.with_columns(
        pl.col("qa_score")
          .rank(method="average")
          .over(["country", "tier"])
          .alias("_qa_rank")
    )
    df = df.with_columns(
        (pl.col("_qa_rank") / pl.col("_qa_rank").max().over(["country", "tier"]))
          .alias("_pct_rank")
    )
    df = df.with_columns(
        pl.when(pl.col("_pct_rank") <= 0.25).then(pl.lit("Q1"))
          .when(pl.col("_pct_rank") <= 0.5).then(pl.lit("Q2"))
          .when(pl.col("_pct_rank") <= 0.75).then(pl.lit("Q3"))
          .otherwise(pl.lit("Q4"))
          .alias("qa_percentile_band")
    )
    df = df.drop(["_qa_rank", "_pct_rank"])

    # 4. Z-score of revenue within merchant (ddof=1)
    df = df.with_columns([
        pl.col("revenue").mean().over("merchant_id").alias("_m_mean"),
        pl.col("revenue").std(ddof=1).over("merchant_id").alias("_m_std"),
    ])
    df = df.with_columns(
        ((pl.col("revenue") - pl.col("_m_mean")) / pl.col("_m_std"))
          .fill_null(0.0)
          .fill_nan(0.0)
          .alias("z_score")
    )
    df = df.with_columns(
        (pl.col("z_score").abs() > 2).cast(pl.Int8).alias("is_anomaly")
    )
    df = df.drop(["_m_mean", "_m_std"])

    # 5. Cumulative revenue within (merchant_id, event_month)
    df = df.with_columns(
        pl.col("revenue").cum_sum().over(["merchant_id", "event_month"]).alias("monthly_cumulative_revenue")
    )

    # 6. Month-over-month revenue growth
    monthly = (
        df.group_by(["merchant_id", "event_month"])
        .agg(pl.col("revenue").sum().alias("monthly_revenue"))
        .sort(["merchant_id", "event_month"])
    )
    monthly = monthly.with_columns(
        pl.col("monthly_revenue").shift(1).over("merchant_id").alias("prev_monthly_revenue")
    )
    monthly = monthly.with_columns(
        ((pl.col("monthly_revenue") - pl.col("prev_monthly_revenue"))
         / pl.col("prev_monthly_revenue")).alias("mom_revenue_growth")
    )
    monthly = monthly.select(["merchant_id", "event_month", "mom_revenue_growth"])

    df = df.join(monthly, on=["merchant_id", "event_month"], how="left")

    # Select & round
    output_cols = [
        "row_id", "merchant_id", "country", "tier",
        "event_date", "event_month", "revenue", "cost", "qa_score",
        "rolling_30d_revenue", "revenue_rank", "qa_percentile_band",
        "z_score", "is_anomaly",
        "monthly_cumulative_revenue", "mom_revenue_growth",
    ]
    result = df.select(output_cols)
    float_cols = [c for c, t in zip(result.columns, result.dtypes) if t == pl.Float64]
    result = result.with_columns([pl.col(c).round(6) for c in float_cols])
    result = result.sort(["merchant_id", "event_date", "row_id"])

    return result


# ---------------------------------------------------------------------------
# Step 2: country_summary.parquet
# ---------------------------------------------------------------------------

def build_country_summary(df: pl.DataFrame) -> pl.DataFrame:
    df = df.filter(pl.col("has_answer") == 1)

    # Revenue per merchant per country
    merchant_rev = (
        df.group_by(["country", "merchant_id"])
        .agg(pl.col("revenue").sum().alias("revenue"))
    )

    # HHI
    country_total = (
        merchant_rev.group_by("country")
        .agg(pl.col("revenue").sum().alias("total_revenue"))
    )
    mr_with_total = merchant_rev.join(country_total, on="country")
    mr_with_total = mr_with_total.with_columns(
        (pl.col("revenue") / pl.col("total_revenue")).alias("_share")
    )
    hhi = (
        mr_with_total.group_by("country")
        .agg((pl.col("_share") ** 2).sum().alias("hhi"))
    )

    # Top-3 merchant share
    def _top3_share(group: pl.DataFrame) -> pl.DataFrame:
        total = group["revenue"].sum()
        top3_rev = group.sort("revenue", descending=True).head(3)["revenue"].sum()
        return pl.DataFrame({
            "country": [group["country"][0]],
            "top3_share": [top3_rev / total if total != 0 else 0.0],
        })

    top3 = merchant_rev.group_by("country", maintain_order=True).map_groups(_top3_share)

    # Merchant count
    mc = (
        merchant_rev.group_by("country")
        .agg(pl.col("merchant_id").n_unique().alias("merchant_count"))
    )

    # Gini coefficient
    def _gini(group: pl.DataFrame) -> pl.DataFrame:
        revs = group["revenue"].sort().to_numpy()
        n = len(revs)
        if n <= 1:
            g = 0.0
        else:
            total = revs.sum()
            if total == 0:
                g = 0.0
            else:
                idx = np.arange(1, n + 1)
                g = float((2.0 * (idx * revs).sum()) / (n * total) - (n + 1) / n)
        return pl.DataFrame({
            "country": [group["country"][0]],
            "gini_coefficient": [g],
        })

    gini = merchant_rev.group_by("country", maintain_order=True).map_groups(_gini)

    # Median merchant revenue
    med = (
        merchant_rev.group_by("country")
        .agg(pl.col("revenue").median().alias("median_merchant_revenue"))
    )

    # Premium share
    premium_rev = (
        df.filter(pl.col("tier") == "premium")
        .group_by("country")
        .agg(pl.col("revenue").sum().alias("premium_revenue"))
    )
    total_rev = (
        df.group_by("country")
        .agg(pl.col("revenue").sum().alias("total_revenue"))
    )
    ps = total_rev.join(premium_rev, on="country", how="left")
    ps = ps.with_columns(pl.col("premium_revenue").fill_null(0.0))
    ps = ps.with_columns(
        (pl.col("premium_revenue") / pl.col("total_revenue")).alias("premium_share")
    )
    ps = ps.select(["country", "premium_share"])

    # Combine
    result = hhi
    for other in [top3, mc, gini, med]:
        result = result.join(other, on="country")
    result = result.join(ps, on="country")

    result = result.select([
        "country", "hhi", "top3_share", "merchant_count",
        "gini_coefficient", "median_merchant_revenue", "premium_share",
    ])
    float_cols = [c for c, t in zip(result.columns, result.dtypes) if t == pl.Float64]
    result = result.with_columns([pl.col(c).round(6) for c in float_cols])
    result = result.sort("country")

    return result


# ---------------------------------------------------------------------------
# Step 3: Schema detection + V2 handling
# ---------------------------------------------------------------------------

ERROR_PRIORITY = [
    "NULL_REQUIRED",
    "INVALID_DATE",
    "NEGATIVE_AMOUNT",
    "MISSING_MERCHANT",
    "INACTIVE_MERCHANT",
]


def detect_schema_version(in_dir: Path) -> str:
    if (in_dir / "input_v2.parquet").exists():
        return "v2"
    return "v1"


def quarantine_rows(
    df_v2: pl.DataFrame, merchants_df: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Split v2 input into valid and quarantine DataFrames."""
    # Build merchant lookup
    merchant_lookup = {}
    for row in merchants_df.iter_rows(named=True):
        merchant_lookup[row["merchant_code"]] = {
            "merchant_id": row["merchant_id"],
            "tier": row["tier"],
            "is_active": row["is_active"],
        }

    errors = []
    for row in df_v2.iter_rows(named=True):
        error = _classify_row(row, merchant_lookup)
        errors.append(error)

    df_v2 = df_v2.with_columns(
        pl.Series("_error", errors, dtype=pl.Utf8)
    )

    quarantine = df_v2.filter(pl.col("_error").is_not_null())
    quarantine = quarantine.with_columns(pl.col("_error").alias("error_code"))
    quarantine = quarantine.drop("_error")

    valid = df_v2.filter(pl.col("_error").is_null())
    valid = valid.drop("_error")

    return valid, quarantine


def _classify_row(row: dict, merchant_lookup: dict) -> str | None:
    """Return error code for a v2 row, or None if valid."""
    # NULL_REQUIRED
    mc = row.get("merchant_code")
    ctry = row.get("country")
    if mc is None or mc == "" or ctry is None or ctry == "":
        return "NULL_REQUIRED"

    # INVALID_DATE
    ts = row.get("event_ts", "")
    if ts is None or ts == "":
        return "INVALID_DATE"
    try:
        from datetime import datetime
        # Parse ISO format
        dt = datetime.fromisoformat(ts)
        if dt.year != 2024:
            return "INVALID_DATE"
    except (ValueError, TypeError):
        return "INVALID_DATE"

    # NEGATIVE_AMOUNT
    if row.get("revenue_cents", 0) < 0 or row.get("cost_cents", 0) < 0:
        return "NEGATIVE_AMOUNT"

    # MISSING_MERCHANT
    if mc not in merchant_lookup:
        return "MISSING_MERCHANT"

    # INACTIVE_MERCHANT
    if not merchant_lookup[mc]["is_active"]:
        return "INACTIVE_MERCHANT"

    return None


def convert_v2_to_v1(
    valid_v2: pl.DataFrame, merchants_df: pl.DataFrame
) -> pl.DataFrame:
    """Convert valid v2 rows to v1 schema."""
    df = valid_v2.join(
        merchants_df.select(["merchant_code", "merchant_id", "tier"]),
        on="merchant_code",
        how="left",
    )

    df = df.with_columns([
        pl.col("event_ts").str.to_datetime("%Y-%m-%dT%H:%M:%S%z", time_zone="UTC").alias("event_date"),
        (pl.col("revenue_cents").cast(pl.Float64) / 100.0).alias("revenue"),
        (pl.col("cost_cents").cast(pl.Float64) / 100.0).alias("cost"),
    ])
    df = df.with_columns(
        pl.col("event_date").dt.strftime("%Y-%m").alias("event_month")
    )

    v1_cols = [
        "row_id", "doc_id", "question_id", "qa_id",
        "question", "context", "title", "answer",
        "merchant_id", "country", "event_date", "event_month",
        "revenue", "cost", "tier",
    ]
    return df.select(v1_cols)


# ---------------------------------------------------------------------------
# Step 3: Enriched Transactions
# ---------------------------------------------------------------------------

ENRICHED_COLS = [
    "row_id", "merchant_id", "country", "tier", "segment",
    "event_date", "event_month",
    "revenue", "cost", "margin", "margin_pct", "net_revenue", "profit_flag",
    "qa_score", "is_premium", "has_answer",
    "context_bucket", "category_label", "priority", "sla_hours",
    "rolling_30d_revenue", "revenue_rank", "qa_percentile_band",
    "z_score", "is_anomaly",
    "monthly_cumulative_revenue", "mom_revenue_growth",
]


def build_enriched_transactions(
    df_v1: pl.DataFrame,
    merchants_df: pl.DataFrame,
    categories_df: pl.DataFrame,
) -> pl.DataFrame:
    df = _ensure_columns(df_v1)

    # Join segment from merchants
    df = df.join(
        merchants_df.select(["merchant_id", "segment"]),
        on="merchant_id",
        how="left",
    )

    # Join categories on context_bucket
    df = df.join(categories_df, on="context_bucket", how="left")

    # Add step 2 analytics (filter to has_answer==1 happens inside)
    df = _step2_analytics(df)

    result = df.select(ENRICHED_COLS)
    float_cols = [c for c, t in zip(result.columns, result.dtypes) if t == pl.Float64]
    result = result.with_columns([pl.col(c).round(6) for c in float_cols])
    result = result.sort(["merchant_id", "event_date", "row_id"])
    return result


def _step2_analytics(df: pl.DataFrame) -> pl.DataFrame:
    """Add all step 2 window columns. Filters to has_answer==1."""
    df = df.filter(pl.col("has_answer") == 1)
    df = df.sort(["merchant_id", "event_date", "row_id"])

    # Rolling 30d
    def _rolling_30d(group_df: pl.DataFrame) -> pl.DataFrame:
        dates = group_df["event_date"].to_list()
        revenues = group_df["revenue"].to_list()
        n = len(dates)
        result = []
        for i in range(n):
            current_date = dates[i]
            total = 0.0
            for j in range(i, -1, -1):
                diff = (current_date - dates[j]).total_seconds()
                if diff < 30 * 86400:  # 30 days in seconds, strictly less (pandas rolling is half-open)
                    total += revenues[j]
                else:
                    break
            result.append(total)
        return group_df.with_columns(
            pl.Series("rolling_30d_revenue", result, dtype=pl.Float64)
        )

    df = df.group_by("merchant_id", maintain_order=True).map_groups(_rolling_30d)
    df = df.sort(["merchant_id", "event_date", "row_id"])

    # Revenue rank
    df = df.with_columns(
        pl.col("revenue")
          .rank(method="dense", descending=True)
          .over(["country", "tier"])
          .cast(pl.Int64)
          .alias("revenue_rank")
    )

    # QA percentile band
    df = df.with_columns(
        pl.col("qa_score")
          .rank(method="average")
          .over(["country", "tier"])
          .alias("_qa_rank")
    )
    df = df.with_columns(
        (pl.col("_qa_rank") / pl.col("_qa_rank").max().over(["country", "tier"]))
          .alias("_pct_rank")
    )
    df = df.with_columns(
        pl.when(pl.col("_pct_rank") <= 0.25).then(pl.lit("Q1"))
          .when(pl.col("_pct_rank") <= 0.5).then(pl.lit("Q2"))
          .when(pl.col("_pct_rank") <= 0.75).then(pl.lit("Q3"))
          .otherwise(pl.lit("Q4"))
          .alias("qa_percentile_band")
    )
    df = df.drop(["_qa_rank", "_pct_rank"])

    # Z-score
    df = df.with_columns([
        pl.col("revenue").mean().over("merchant_id").alias("_m_mean"),
        pl.col("revenue").std(ddof=1).over("merchant_id").alias("_m_std"),
    ])
    df = df.with_columns(
        ((pl.col("revenue") - pl.col("_m_mean")) / pl.col("_m_std"))
          .fill_null(0.0)
          .fill_nan(0.0)
          .alias("z_score")
    )
    df = df.with_columns(
        (pl.col("z_score").abs() > 2).cast(pl.Int8).alias("is_anomaly")
    )
    df = df.drop(["_m_mean", "_m_std"])

    # Monthly cumulative
    df = df.with_columns(
        pl.col("revenue").cum_sum().over(["merchant_id", "event_month"]).alias("monthly_cumulative_revenue")
    )

    # MoM growth
    monthly = (
        df.group_by(["merchant_id", "event_month"])
        .agg(pl.col("revenue").sum().alias("monthly_revenue"))
        .sort(["merchant_id", "event_month"])
    )
    monthly = monthly.with_columns(
        pl.col("monthly_revenue").shift(1).over("merchant_id").alias("prev_monthly_revenue")
    )
    monthly = monthly.with_columns(
        ((pl.col("monthly_revenue") - pl.col("prev_monthly_revenue"))
         / pl.col("prev_monthly_revenue")).alias("mom_revenue_growth")
    )
    monthly = monthly.select(["merchant_id", "event_month", "mom_revenue_growth"])

    df = df.join(monthly, on=["merchant_id", "event_month"], how="left")

    return df


# ---------------------------------------------------------------------------
# Step 3: quality_v2.json
# ---------------------------------------------------------------------------

def build_quality_v2(
    df_v2_all: pl.DataFrame,
    quarantine_df: pl.DataFrame,
    enriched_df: pl.DataFrame,
    df_v1_valid: pl.DataFrame,
) -> dict:
    df = _ensure_columns(df_v1_valid)
    filt = df.filter(pl.col("has_answer") == 1)

    counts = filt.group_by("country").agg(pl.col("row_id").count().alias("cnt"))
    max_count = counts["cnt"].max()
    top_countries = counts.filter(pl.col("cnt") == max_count)["country"].sort().to_list()
    top_country = top_countries[0]

    max_event = filt["event_date"].max()
    run_id = max_event.strftime("%Y%m%d-000000")

    quarantine_by_error = {}
    if "error_code" in quarantine_df.columns and len(quarantine_df) > 0:
        ec = quarantine_df.group_by("error_code").agg(pl.col("error_code").count().alias("cnt"))
        for row in ec.iter_rows(named=True):
            quarantine_by_error[row["error_code"]] = row["cnt"]
    for code in ERROR_PRIORITY:
        quarantine_by_error.setdefault(code, 0)

    return {
        "schema_version": "v2",
        "total_input_rows": int(len(df_v2_all)),
        "valid_rows": int(len(df_v1_valid)),
        "quarantined_rows": int(len(quarantine_df)),
        "quarantine_by_error": dict(sorted(quarantine_by_error.items())),
        "join_match_rate": round(
            float(len(enriched_df) / len(df_v1_valid)) if len(df_v1_valid) else 0.0, 6
        ),
        "row_count": int(len(filt)),
        "distinct_merchants": int(filt["merchant_id"].n_unique()),
        "mean_qa_score": round(float(filt["qa_score"].mean()), 6),
        "pct_premium": round(float((filt["tier"] == "premium").mean()), 6),
        "top_country": top_country,
        "run_id": run_id,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    version = detect_schema_version(in_dir)

    if version == "v1":
        df = pl.scan_parquet(in_dir / "input.parquet").collect()
        df = _ensure_columns(df)

        _build_step1_outputs(df, out_dir)

        analytics = build_merchant_analytics(df)
        analytics.write_parquet(out_dir / "merchant_analytics.parquet")

        csummary = build_country_summary(df)
        csummary.write_parquet(out_dir / "country_summary.parquet")

    else:
        df_v2 = pl.scan_parquet(in_dir / "input_v2.parquet").collect()
        merchants_df = pl.scan_parquet(in_dir / "merchants.parquet").collect()
        categories_df = pl.scan_parquet(in_dir / "categories.parquet").collect()

        # Quarantine
        valid_v2, quarantine = quarantine_rows(df_v2, merchants_df)

        # Convert to v1
        df_v1 = convert_v2_to_v1(valid_v2, merchants_df)
        df = _ensure_columns(df_v1)

        # Step 1 outputs
        _build_step1_outputs(df, out_dir)

        # Step 2 outputs
        analytics = build_merchant_analytics(df)
        analytics.write_parquet(out_dir / "merchant_analytics.parquet")

        csummary = build_country_summary(df)
        csummary.write_parquet(out_dir / "country_summary.parquet")

        # Step 3 outputs
        enriched = build_enriched_transactions(df_v1, merchants_df, categories_df)
        enriched.write_parquet(out_dir / "enriched_transactions.parquet")

        quarantine_out = quarantine.select(list(df_v2.columns) + ["error_code"])
        quarantine_out = quarantine_out.sort("row_id")
        quarantine_out.write_parquet(out_dir / "quarantine.parquet")

        quality = build_quality_v2(df_v2, quarantine_out, enriched, df_v1)
        (out_dir / "quality_v2.json").write_text(
            json.dumps(quality, sort_keys=True, separators=(",", ":")) + "\n"
        )


if __name__ == "__main__":
    main()
