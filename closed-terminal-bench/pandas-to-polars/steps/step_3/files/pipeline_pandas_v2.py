"""Step 3: Schema Evolution + Data Quarantine — pandas reference implementation.

READ-ONLY. Shows how the pandas pipeline handles v2 input schema,
joins with reference tables, quarantines bad rows, and produces enriched
output. Translate this logic to Polars in /app/step_1/files/pipeline_polars.py.

Run (for reference only):
    python3 pipeline_pandas_v2.py --in <input_dir> --out <output_dir>

If <input_dir> contains input_v2.parquet, runs v2 mode.
Otherwise, reads input.parquet and runs v1 mode (step 1+2 only).
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_dir", required=True)
    p.add_argument("--out", dest="out_dir", required=True)
    return p.parse_args()


# ── _ensure_columns (same as Step 1) ──────────────────────────────────────


def _bucketize(tokens: pd.Series, short_max: int, medium_max: int) -> pd.Series:
    return pd.Series(
        np.select(
            [tokens < short_max, tokens < medium_max],
            ["short", "medium"],
            default="long",
        ),
        index=tokens.index,
    )


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "event_date" in df.columns:
        df["event_date"] = pd.to_datetime(df["event_date"], utc=True)
    else:
        df["event_date"] = pd.Timestamp("2024-01-01", tz="UTC")

    for col in ["question", "context", "title", "answer", "country", "tier"]:
        df[col] = df[col].fillna("").astype("string")

    df["doc_id"] = df["doc_id"].astype("int64")
    df["question_id"] = df["question_id"].astype("int64")
    df["qa_id"] = df["qa_id"].astype("int64")

    df["question_length"] = df["question"].str.len().astype("int64")
    df["context_length"] = df["context"].str.len().astype("int64")
    df["answer_length"] = df["answer"].str.len().astype("int64")
    df["title_length"] = df["title"].str.len().astype("int64")

    df["question_tokens"] = df["question"].str.findall(r"\S+").str.len().fillna(0).astype("int64")
    df["context_tokens"] = df["context"].str.findall(r"\S+").str.len().fillna(0).astype("int64")
    df["answer_tokens"] = df["answer"].str.findall(r"\S+").str.len().fillna(0).astype("int64")
    df["title_tokens"] = df["title"].str.findall(r"\S+").str.len().fillna(0).astype("int64")

    df["has_answer"] = (df["answer_length"] > 0).astype("int8")
    df["is_long_context"] = (df["context_tokens"] >= 360).astype("int8")

    df["context_bucket"] = _bucketize(df["context_tokens"], 120, 360)
    df["question_bucket"] = _bucketize(df["question_tokens"], 12, 22)

    df["event_month"] = df["event_date"].dt.strftime("%Y-%m")

    df["margin"] = df["revenue"] - df["cost"]
    df["margin_pct"] = np.where(df["revenue"] != 0, df["margin"] / df["revenue"], 0.0)

    df["net_revenue"] = df["revenue"] - df["cost"]
    df["profit_flag"] = (df["net_revenue"] >= 25).astype("int8")

    df["qa_score"] = (
        (df["question_tokens"] * 1.3 + df["answer_tokens"] * 2.1)
        / (df["context_tokens"] + 10)
    ).astype("float64")

    df["is_premium"] = (df["tier"] == "premium").astype("int8")

    return df


# ── V2 Schema Handling ────────────────────────────────────────────────────

ERROR_PRIORITY = [
    "NULL_REQUIRED",
    "INVALID_DATE",
    "NEGATIVE_AMOUNT",
    "MISSING_MERCHANT",
    "INACTIVE_MERCHANT",
]


def detect_schema_version(in_dir: Path) -> str:
    """Detect input schema version by filename."""
    if (in_dir / "input_v2.parquet").exists():
        return "v2"
    return "v1"


def classify_row(row: pd.Series, merchant_lookup: dict) -> str | None:
    """Return error code for a v2 row, or None if valid.

    Priority: NULL_REQUIRED > INVALID_DATE > NEGATIVE_AMOUNT >
              MISSING_MERCHANT > INACTIVE_MERCHANT
    """
    # NULL_REQUIRED: null in merchant_code or country
    mc = row.get("merchant_code")
    ctry = row.get("country")
    if pd.isna(mc) or mc == "" or pd.isna(ctry) or ctry == "":
        return "NULL_REQUIRED"

    # INVALID_DATE: unparseable event_ts or year != 2024
    ts = row.get("event_ts", "")
    if pd.isna(ts) or ts == "":
        return "INVALID_DATE"
    try:
        dt = pd.Timestamp(ts)
        if dt.year != 2024:
            return "INVALID_DATE"
    except (ValueError, TypeError):
        return "INVALID_DATE"

    # NEGATIVE_AMOUNT: revenue_cents or cost_cents < 0
    if row.get("revenue_cents", 0) < 0 or row.get("cost_cents", 0) < 0:
        return "NEGATIVE_AMOUNT"

    # MISSING_MERCHANT: merchant_code not in merchants table
    if mc not in merchant_lookup:
        return "MISSING_MERCHANT"

    # INACTIVE_MERCHANT: is_active == False
    if not merchant_lookup[mc]["is_active"]:
        return "INACTIVE_MERCHANT"

    return None


def quarantine_rows(
    df_v2: pd.DataFrame, merchants_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split v2 input into valid and quarantine DataFrames."""
    merchant_lookup = {}
    for _, row in merchants_df.iterrows():
        merchant_lookup[row["merchant_code"]] = {
            "merchant_id": row["merchant_id"],
            "tier": row["tier"],
            "is_active": row["is_active"],
        }

    errors = []
    for idx, row in df_v2.iterrows():
        errors.append(classify_row(row, merchant_lookup))

    df_v2 = df_v2.copy()
    df_v2["_error"] = errors

    quarantine = df_v2[df_v2["_error"].notna()].copy()
    quarantine["error_code"] = quarantine["_error"]
    quarantine = quarantine.drop(columns=["_error"])

    valid = df_v2[df_v2["_error"].isna()].copy()
    valid = valid.drop(columns=["_error"])

    return valid, quarantine


def convert_v2_to_v1(
    valid_v2: pd.DataFrame, merchants_df: pd.DataFrame
) -> pd.DataFrame:
    """Convert valid v2 rows back to v1 schema.

    - merchant_code → merchant_id (via merchants table join)
    - event_ts → event_date (parse ISO string to UTC datetime)
    - revenue_cents → revenue (/ 100.0)
    - cost_cents → cost (/ 100.0)
    - tier restored from merchants table
    - event_month derived from event_date
    """
    df = valid_v2.merge(
        merchants_df[["merchant_code", "merchant_id", "tier"]],
        on="merchant_code",
        how="left",
    )

    df["event_date"] = pd.to_datetime(df["event_ts"], utc=True)
    df["revenue"] = df["revenue_cents"] / 100.0
    df["cost"] = df["cost_cents"] / 100.0
    df["event_month"] = df["event_date"].dt.strftime("%Y-%m")

    v1_cols = [
        "row_id", "doc_id", "question_id", "qa_id",
        "question", "context", "title", "answer",
        "merchant_id", "country", "event_date", "event_month",
        "revenue", "cost", "tier",
    ]
    return df[v1_cols].copy()


# ── Step 2 Analytics (same as pipeline_pandas_advanced.py) ────────────────


def _step2_analytics(df: pd.DataFrame) -> pd.DataFrame:
    """Add all step 2 window columns to _ensure_columns'd DataFrame.

    Returns filtered (has_answer==1) DataFrame with analytics columns.
    """
    df = df[df["has_answer"] == 1].copy()
    df = df.sort_values(["merchant_id", "event_date", "row_id"]).reset_index(drop=True)

    # Rolling 30d
    df["rolling_30d_revenue"] = (
        df.groupby("merchant_id")
        .apply(
            lambda g: g.set_index("event_date")["revenue"]
            .rolling("30D").sum()
            .reset_index(level=0, drop=True)
        )
        .droplevel(0).sort_index().values
    )

    # Revenue rank
    df["revenue_rank"] = (
        df.groupby(["country", "tier"])["revenue"]
        .rank(method="dense", ascending=False).astype("int64")
    )

    # QA percentile band
    prank = df.groupby(["country", "tier"])["qa_score"].transform(
        lambda s: s.rank(pct=True, method="average")
    )
    df["qa_percentile_band"] = pd.cut(
        prank, bins=[0, 0.25, 0.5, 0.75, 1.0],
        labels=["Q1", "Q2", "Q3", "Q4"], include_lowest=True,
    ).astype(str)

    # Z-score
    merchant_mean = df.groupby("merchant_id")["revenue"].transform("mean")
    merchant_std = df.groupby("merchant_id")["revenue"].transform("std")
    df["z_score"] = (df["revenue"] - merchant_mean) / merchant_std
    df["z_score"] = df["z_score"].fillna(0.0)
    df["is_anomaly"] = (df["z_score"].abs() > 2).astype("int8")

    # Monthly cumulative
    df["monthly_cumulative_revenue"] = df.groupby(
        ["merchant_id", "event_month"]
    )["revenue"].cumsum()

    # MoM growth
    monthly = (
        df.groupby(["merchant_id", "event_month"], as_index=False)["revenue"]
        .sum().rename(columns={"revenue": "monthly_revenue"})
        .sort_values(["merchant_id", "event_month"])
    )
    monthly["prev_monthly_revenue"] = monthly.groupby("merchant_id")[
        "monthly_revenue"
    ].shift(1)
    monthly["mom_revenue_growth"] = (
        (monthly["monthly_revenue"] - monthly["prev_monthly_revenue"])
        / monthly["prev_monthly_revenue"]
    )
    df = df.merge(
        monthly[["merchant_id", "event_month", "mom_revenue_growth"]],
        on=["merchant_id", "event_month"], how="left",
    )

    return df


# ── Enriched Transactions (Step 3 output) ─────────────────────────────────


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
    df_v1: pd.DataFrame,
    merchants_df: pd.DataFrame,
    categories_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build enriched_transactions.parquet from valid v1-converted data.

    Joins with merchants (segment) and categories (category_label, priority,
    sla_hours), then adds all step 2 window function columns.
    """
    df = _ensure_columns(df_v1)

    # Join segment from merchants
    df = df.merge(
        merchants_df[["merchant_id", "segment"]],
        on="merchant_id", how="left",
    )

    # Join categories on context_bucket
    df = df.merge(categories_df, on="context_bucket", how="left")

    # Add step 2 analytics
    df = _step2_analytics(df)

    result = df[ENRICHED_COLS].copy()
    for col in result.select_dtypes(include=["float64"]).columns:
        result[col] = result[col].round(6)
    result = result.sort_values(
        ["merchant_id", "event_date", "row_id"]
    ).reset_index(drop=True)
    return result


def build_quality_v2(
    df_v2_all: pd.DataFrame,
    quarantine_df: pd.DataFrame,
    enriched_df: pd.DataFrame,
    df_v1_valid: pd.DataFrame,
) -> dict:
    """Build quality_v2.json metrics."""
    df = _ensure_columns(df_v1_valid)
    filt = df[df["has_answer"] == 1].copy()

    counts = filt["country"].value_counts()
    max_count = counts.max()
    top_country = sorted(counts[counts == max_count].index.tolist())[0]
    max_event = filt["event_date"].max()
    run_id = max_event.strftime("%Y%m%d-000000")

    quarantine_by_error = quarantine_df["error_code"].value_counts().to_dict()
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
        "distinct_merchants": int(filt["merchant_id"].nunique()),
        "mean_qa_score": round(float(filt["qa_score"].mean()), 6),
        "pct_premium": round(float((filt["tier"] == "premium").mean()), 6),
        "top_country": top_country,
        "run_id": run_id,
    }


# ── Step 1 Outputs (unchanged) ───────────────────────────────────────────

# (import from pipeline_pandas.py or inline; shown here for completeness)


def _build_step1_outputs(df: pd.DataFrame, out_dir: Path) -> None:
    """Produce step 1 outputs: summary.parquet, top_merchants.csv, quality.json."""
    filt = df[df["has_answer"] == 1].copy()

    summary = (
        filt.groupby(
            ["country", "tier", "event_month", "context_bucket"], as_index=False
        )
        .agg(
            rows=("row_id", "count"),
            avg_revenue=("revenue", "mean"),
            avg_margin_pct=("margin_pct", "mean"),
            p90_qa_score=("qa_score", lambda s: s.quantile(0.9, interpolation="linear")),
            profit_rate=("profit_flag", "mean"),
        )
        .sort_values(["event_month", "country", "tier", "context_bucket"])
        .reset_index(drop=True)
    )
    summary[["avg_revenue", "avg_margin_pct", "p90_qa_score", "profit_rate"]] = (
        summary[["avg_revenue", "avg_margin_pct", "p90_qa_score", "profit_rate"]].round(6)
    )
    summary.to_parquet(out_dir / "summary.parquet", index=False)

    merchants = (
        filt.groupby(["country", "merchant_id"], as_index=False)
        .agg(
            merchant_rows=("row_id", "count"),
            merchant_revenue=("revenue", "sum"),
            merchant_margin=("margin", "sum"),
            merchant_avg_qa=("qa_score", "mean"),
        )
        .sort_values(
            ["country", "merchant_revenue", "merchant_margin", "merchant_id"],
            ascending=[True, False, False, True],
        )
    )
    top_merchants = (
        merchants.groupby("country", as_index=False)
        .head(3)
        .loc[:, ["country", "merchant_id", "merchant_revenue", "merchant_margin", "merchant_avg_qa"]]
        .sort_values(["country", "merchant_revenue", "merchant_id"], ascending=[True, False, True])
        .reset_index(drop=True)
    )
    top_merchants[["merchant_revenue", "merchant_margin", "merchant_avg_qa"]] = (
        top_merchants[["merchant_revenue", "merchant_margin", "merchant_avg_qa"]].round(6)
    )
    top_merchants.to_csv(out_dir / "top_merchants.csv", index=False, float_format="%.6f")

    counts = filt["country"].value_counts()
    max_count = counts.max()
    top_country = sorted(counts[counts == max_count].index.tolist())[0]
    max_event = filt["event_date"].max()
    run_id = max_event.strftime("%Y%m%d-000000")

    quality = {
        "row_count": int(len(filt)),
        "distinct_merchants": int(filt["merchant_id"].nunique()),
        "mean_qa_score": round(float(filt["qa_score"].mean()), 6),
        "pct_premium": round(float(filt["is_premium"].mean()), 6),
        "top_country": top_country,
        "run_id": run_id,
    }
    (out_dir / "quality.json").write_text(
        json.dumps(quality, sort_keys=True, separators=(",", ":")) + "\n"
    )


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()
    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    version = detect_schema_version(in_dir)

    if version == "v1":
        # Step 1+2 only (unchanged from pipeline_pandas_advanced.py)
        df = pd.read_parquet(in_dir / "input.parquet")
        df = _ensure_columns(df)
        _build_step1_outputs(df, out_dir)
        # Step 2 analytics...
        from pipeline_pandas_advanced import build_merchant_analytics, build_country_summary
        analytics = build_merchant_analytics(df)
        analytics.to_parquet(out_dir / "merchant_analytics.parquet", index=False)
        summary = build_country_summary(df)
        summary.to_parquet(out_dir / "country_summary.parquet", index=False)
    else:
        # V2 mode: full pipeline
        df_v2 = pd.read_parquet(in_dir / "input_v2.parquet")
        merchants_df = pd.read_parquet(in_dir / "merchants.parquet")
        categories_df = pd.read_parquet(in_dir / "categories.parquet")

        # Quarantine
        valid_v2, quarantine = quarantine_rows(df_v2, merchants_df)

        # Convert to v1
        df_v1 = convert_v2_to_v1(valid_v2, merchants_df)
        df = _ensure_columns(df_v1)

        # Step 1 outputs
        _build_step1_outputs(df, out_dir)

        # Step 2 outputs (merchant_analytics, country_summary)
        from pipeline_pandas_advanced import build_merchant_analytics, build_country_summary
        analytics = build_merchant_analytics(df)
        analytics.to_parquet(out_dir / "merchant_analytics.parquet", index=False)
        csummary = build_country_summary(df)
        csummary.to_parquet(out_dir / "country_summary.parquet", index=False)

        # Step 3 outputs
        enriched = build_enriched_transactions(df_v1, merchants_df, categories_df)
        enriched.to_parquet(out_dir / "enriched_transactions.parquet", index=False)

        quarantine_out = quarantine[list(df_v2.columns) + ["error_code"]].copy()
        quarantine_out = quarantine_out.sort_values("row_id").reset_index(drop=True)
        quarantine_out.to_parquet(out_dir / "quarantine.parquet", index=False)

        quality = build_quality_v2(df_v2, quarantine_out, enriched, df_v1)
        (out_dir / "quality_v2.json").write_text(
            json.dumps(quality, sort_keys=True, separators=(",", ":")) + "\n"
        )


if __name__ == "__main__":
    main()
