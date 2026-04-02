#!/usr/bin/env python3
"""Generate expected data and outputs for pandas-to-polars Step 3.

Transforms step 1 inputs to v2 schema, generates reference tables
(merchants.parquet, categories.parquet), injects quarantine rows,
and computes expected outputs.

Usage:
    python3 scripts/generate_step3_data.py
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

TASK_DIR = Path(__file__).resolve().parent.parent

# Import step 2 generation functions
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_step2_data import (
    _bucketize,
    _ensure_columns,
    build_country_summary,
    build_merchant_analytics,
)

COUNTRY_CURRENCY = {
    "US": "USD",
    "GB": "GBP",
    "DE": "EUR",
    "FR": "EUR",
    "CA": "CAD",
    "IN": "INR",
    "AU": "AUD",
    "JP": "JPY",
}

CHANNELS = ["online", "mobile", "in_store"]

# Error code priority (first match wins)
ERROR_CODES = [
    "NULL_REQUIRED",
    "INVALID_DATE",
    "NEGATIVE_AMOUNT",
    "MISSING_MERCHANT",
    "INACTIVE_MERCHANT",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_merchants_table(all_merchant_ids: set[int]) -> pd.DataFrame:
    """Generate merchants.parquet reference table.

    Covers merchant_ids 0-4999.  ~5% inactive, but only 3 specific
    data-bearing ids are inactive (to control quarantine count).
    """
    rng = np.random.default_rng(42)

    ids = np.arange(5000)
    df = pd.DataFrame({"merchant_id": ids})
    df["merchant_code"] = df["merchant_id"].apply(lambda x: f"M{x:05d}")
    df["tier"] = np.where(df["merchant_id"] % 5 == 0, "premium", "standard")

    segments = ["enterprise", "smb", "startup"]
    df["segment"] = [segments[mid % 3] for mid in df["merchant_id"]]

    base = pd.Timestamp("2023-01-01")
    df["onboarding_date"] = [
        base + pd.Timedelta(days=int(mid % 365)) for mid in df["merchant_id"]
    ]

    # 5% inactive: pick 250 ids, but ensure exactly 3 are in our data
    # First find ids NOT in either dataset
    not_in_data = sorted(set(range(5000)) - all_merchant_ids)

    # Pick 3 data-bearing ids to make inactive (choose rare ones — single-tx)
    # We'll use deterministic picks: the 3 smallest merchant_ids in data
    sorted_data_ids = sorted(all_merchant_ids)
    inactive_data_ids = set(sorted_data_ids[:3])

    # Fill remaining ~247 inactive from non-data ids
    rng.shuffle(np.array(not_in_data))  # deterministic shuffle
    inactive_non_data = set(list(not_in_data)[:247])
    inactive_set = inactive_data_ids | inactive_non_data

    df["is_active"] = ~df["merchant_id"].isin(inactive_set)

    return df


def generate_categories_table() -> pd.DataFrame:
    """Generate categories.parquet reference table."""
    return pd.DataFrame(
        {
            "context_bucket": ["short", "medium", "long"],
            "category_label": [
                "Quick Reference",
                "Standard Analysis",
                "Deep Research",
            ],
            "priority": [1, 2, 3],
            "sla_hours": [24, 48, 72],
        }
    )


def transform_to_v2(df_v1: pd.DataFrame) -> pd.DataFrame:
    """Transform v1 input to v2 schema."""
    df = df_v1.copy()

    # merchant_id → merchant_code
    df["merchant_code"] = df["merchant_id"].apply(lambda x: f"M{x:05d}")

    # event_date → event_ts (ISO string with timezone)
    df["event_ts"] = df["event_date"].dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # revenue/cost → cents (int64)
    df["revenue_cents"] = (df["revenue"] * 100).round().astype("int64")
    df["cost_cents"] = (df["cost"] * 100).round().astype("int64")

    # Add currency and channel
    df["currency"] = df["country"].map(COUNTRY_CURRENCY)
    df["channel"] = [CHANNELS[rid % 3] for rid in df["row_id"]]

    # Select v2 columns (drop v1-only columns)
    v2_cols = [
        "row_id",
        "doc_id",
        "question_id",
        "qa_id",
        "question",
        "context",
        "title",
        "answer",
        "merchant_code",
        "country",
        "event_ts",
        "revenue_cents",
        "cost_cents",
        "currency",
        "channel",
    ]
    return df[v2_cols].copy()


def inject_quarantine_rows(
    df_v2: pd.DataFrame, merchants_df: pd.DataFrame
) -> pd.DataFrame:
    """Inject ~19 bad rows into v2 input."""
    max_row_id = df_v2["row_id"].max()
    next_id = max_row_id + 1

    base = {
        "doc_id": 1,
        "question_id": 1,
        "qa_id": 1,
        "question": "test question for quarantine",
        "context": "test context for quarantine row validation",
        "title": "test",
        "answer": "test answer",
        "merchant_code": "M00100",
        "country": "US",
        "event_ts": "2024-06-15T00:00:00+00:00",
        "revenue_cents": 5000,
        "cost_cents": 2000,
        "currency": "USD",
        "channel": "online",
    }

    bad_rows = []

    # NULL_REQUIRED (4 rows): null in merchant_code or country
    for i, (mc, ctry) in enumerate(
        [(None, "US"), (None, "GB"), ("M00100", None), (None, None)]
    ):
        row = {**base, "row_id": next_id + len(bad_rows)}
        row["merchant_code"] = mc
        row["country"] = ctry
        if ctry is not None:
            row["currency"] = COUNTRY_CURRENCY.get(ctry, "USD")
        else:
            row["currency"] = None
        bad_rows.append(row)

    # INVALID_DATE (4 rows): unparseable or outside 2024
    bad_dates = [
        "not-a-date",
        "2023-06-15T12:00:00+00:00",
        "2025-03-01T00:00:00+00:00",
        "",
    ]
    for ts in bad_dates:
        row = {**base, "row_id": next_id + len(bad_rows), "event_ts": ts}
        bad_rows.append(row)

    # NEGATIVE_AMOUNT (4 rows): negative revenue_cents or cost_cents
    neg_amounts = [
        (-500, 100),
        (100, -200),
        (-1000, -300),
        (-1, 50),
    ]
    for rev, cost in neg_amounts:
        row = {
            **base,
            "row_id": next_id + len(bad_rows),
            "revenue_cents": rev,
            "cost_cents": cost,
        }
        bad_rows.append(row)

    # MISSING_MERCHANT (4 rows): merchant_code not in merchants table
    for code in ["M90001", "M90002", "M90003", "M90004"]:
        row = {**base, "row_id": next_id + len(bad_rows), "merchant_code": code}
        bad_rows.append(row)

    # INACTIVE_MERCHANT (3 rows): merchant is_active=False
    inactive = merchants_df[
        merchants_df["is_active"] == False  # noqa: E712
    ]["merchant_code"].head(3)
    for code in inactive.values:
        row = {**base, "row_id": next_id + len(bad_rows), "merchant_code": code}
        bad_rows.append(row)

    bad_df = pd.DataFrame(bad_rows)
    # Ensure column order matches
    bad_df = bad_df[df_v2.columns]

    return pd.concat([df_v2, bad_df], ignore_index=True)


def classify_quarantine(
    row: pd.Series, merchants_df: pd.DataFrame
) -> str | None:
    """Return error code for a row, or None if valid.

    Priority: NULL_REQUIRED > INVALID_DATE > NEGATIVE_AMOUNT >
              MISSING_MERCHANT > INACTIVE_MERCHANT
    """
    # NULL_REQUIRED
    if pd.isna(row.get("merchant_code")) or pd.isna(row.get("country")):
        return "NULL_REQUIRED"
    if row["merchant_code"] == "" or row["country"] == "":
        return "NULL_REQUIRED"

    # INVALID_DATE
    ts = row.get("event_ts", "")
    if pd.isna(ts) or ts == "":
        return "INVALID_DATE"
    try:
        dt = pd.Timestamp(ts)
        if dt.year != 2024:
            return "INVALID_DATE"
    except (ValueError, TypeError):
        return "INVALID_DATE"

    # NEGATIVE_AMOUNT
    rev = row.get("revenue_cents", 0)
    cost = row.get("cost_cents", 0)
    if (not pd.isna(rev) and rev < 0) or (not pd.isna(cost) and cost < 0):
        return "NEGATIVE_AMOUNT"

    # MISSING_MERCHANT
    mc = row["merchant_code"]
    if mc not in merchants_df["merchant_code"].values:
        return "MISSING_MERCHANT"

    # INACTIVE_MERCHANT
    match = merchants_df[merchants_df["merchant_code"] == mc]
    if len(match) > 0 and not match.iloc[0]["is_active"]:
        return "INACTIVE_MERCHANT"

    return None


def convert_v2_to_v1(
    df_v2: pd.DataFrame, merchants_df: pd.DataFrame
) -> pd.DataFrame:
    """Convert valid v2 rows back to v1-compatible schema."""
    df = df_v2.copy()

    # Join with merchants to get merchant_id and tier
    df = df.merge(
        merchants_df[["merchant_code", "merchant_id", "tier"]],
        on="merchant_code",
        how="left",
    )

    # event_ts → event_date
    df["event_date"] = pd.to_datetime(df["event_ts"], utc=True)

    # cents → dollars
    df["revenue"] = df["revenue_cents"] / 100.0
    df["cost"] = df["cost_cents"] / 100.0

    # Derive event_month
    df["event_month"] = df["event_date"].dt.strftime("%Y-%m")

    # Select v1 columns
    v1_cols = [
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
    ]
    return df[v1_cols].copy()


ENRICHED_COLS = [
    "row_id",
    "merchant_id",
    "country",
    "tier",
    "segment",
    "event_date",
    "event_month",
    "revenue",
    "cost",
    "margin",
    "margin_pct",
    "net_revenue",
    "profit_flag",
    "qa_score",
    "is_premium",
    "has_answer",
    "context_bucket",
    "category_label",
    "priority",
    "sla_hours",
    "rolling_30d_revenue",
    "revenue_rank",
    "qa_percentile_band",
    "z_score",
    "is_anomaly",
    "monthly_cumulative_revenue",
    "mom_revenue_growth",
]


def build_enriched_transactions(
    df_v1: pd.DataFrame,
    merchants_df: pd.DataFrame,
    categories_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build enriched_transactions.parquet from valid v1-converted data."""
    df = _ensure_columns(df_v1)

    # Join segment from merchants
    df = df.merge(
        merchants_df[["merchant_id", "segment"]],
        on="merchant_id",
        how="left",
    )

    # Join categories on context_bucket
    df = df.merge(
        categories_df,
        on="context_bucket",
        how="left",
    )

    # Compute step 2 analytics (same logic as build_merchant_analytics)
    filt = df[df["has_answer"] == 1].copy()
    filt = filt.sort_values(
        ["merchant_id", "event_date", "row_id"]
    ).reset_index(drop=True)

    # Rolling 30d
    parts = []
    for _, group in filt.groupby("merchant_id"):
        g = group.set_index("event_date")
        g["rolling_30d_revenue"] = g["revenue"].rolling("30D").sum()
        parts.append(g.reset_index())
    filt = pd.concat(parts, ignore_index=True)
    filt = filt.sort_values(
        ["merchant_id", "event_date", "row_id"]
    ).reset_index(drop=True)

    # Revenue rank
    filt["revenue_rank"] = (
        filt.groupby(["country", "tier"])["revenue"]
        .rank(method="dense", ascending=False)
        .astype("int64")
    )

    # QA percentile band
    prank = filt.groupby(["country", "tier"])["qa_score"].rank(
        pct=True, method="average"
    )
    filt["qa_percentile_band"] = pd.cut(
        prank,
        bins=[0, 0.25, 0.5, 0.75, 1.0],
        labels=["Q1", "Q2", "Q3", "Q4"],
        include_lowest=True,
    ).astype(str)

    # Z-score
    grp = filt.groupby("merchant_id")
    merchant_mean = grp["revenue"].transform("mean")
    merchant_std = grp["revenue"].transform("std")
    filt["z_score"] = (filt["revenue"] - merchant_mean) / merchant_std
    filt["z_score"] = filt["z_score"].fillna(0.0)
    filt["is_anomaly"] = (filt["z_score"].abs() > 2).astype("int8")

    # Monthly cumulative
    filt["monthly_cumulative_revenue"] = filt.groupby(
        ["merchant_id", "event_month"]
    )["revenue"].cumsum()

    # MoM growth
    monthly = (
        filt.groupby(["merchant_id", "event_month"], as_index=False)[
            "revenue"
        ]
        .sum()
        .rename(columns={"revenue": "monthly_revenue"})
    )
    monthly = monthly.sort_values(
        ["merchant_id", "event_month"]
    ).reset_index(drop=True)
    monthly["prev_monthly_revenue"] = monthly.groupby("merchant_id")[
        "monthly_revenue"
    ].shift(1)
    monthly["mom_revenue_growth"] = (
        monthly["monthly_revenue"] - monthly["prev_monthly_revenue"]
    ) / monthly["prev_monthly_revenue"]
    filt = filt.merge(
        monthly[["merchant_id", "event_month", "mom_revenue_growth"]],
        on=["merchant_id", "event_month"],
        how="left",
    )

    result = filt[ENRICHED_COLS].copy()

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

    quarantine_by_error = (
        quarantine_df["error_code"].value_counts().to_dict()
    )
    # Ensure all error codes present
    for code in ERROR_CODES:
        quarantine_by_error.setdefault(code, 0)

    return {
        "schema_version": "v2",
        "total_input_rows": int(len(df_v2_all)),
        "valid_rows": int(len(df_v1_valid)),
        "quarantined_rows": int(len(quarantine_df)),
        "quarantine_by_error": dict(
            sorted(quarantine_by_error.items())
        ),
        "join_match_rate": round(
            float(len(enriched_df) / len(df_v1_valid))
            if len(df_v1_valid) > 0
            else 0.0,
            6,
        ),
        "row_count": int(len(filt)),
        "distinct_merchants": int(filt["merchant_id"].nunique()),
        "mean_qa_score": round(float(filt["qa_score"].mean()), 6),
        "pct_premium": round(
            float((filt["tier"] == "premium").mean()), 6
        ),
        "top_country": top_country,
        "run_id": run_id,
    }


def process_dataset(
    v1_input_path: Path,
    step3_data_dir: Path,
    step3_expected_dir: Path,
    merchants_df: pd.DataFrame,
    categories_df: pd.DataFrame,
    is_public: bool = True,
) -> None:
    """Process a single dataset for step 3."""
    df_v1 = pd.read_parquet(v1_input_path)

    # Transform to v2
    df_v2 = transform_to_v2(df_v1)

    # Inject quarantine rows
    df_v2_with_bad = inject_quarantine_rows(df_v2, merchants_df)

    # Write v2 input
    step3_data_dir.mkdir(parents=True, exist_ok=True)
    df_v2_with_bad.to_parquet(
        step3_data_dir / "input_v2.parquet", index=False
    )

    # Copy reference tables
    merchants_df.to_parquet(
        step3_data_dir / "merchants.parquet", index=False
    )
    categories_df.to_parquet(
        step3_data_dir / "categories.parquet", index=False
    )

    # Write schema mapping
    schema_mapping = {
        "v1_to_v2": {
            "merchant_id": "merchant_code",
            "event_date": "event_ts",
            "revenue": "revenue_cents",
            "cost": "cost_cents",
        },
        "removed_columns": ["tier", "event_month"],
        "added_columns": ["currency", "channel"],
        "type_changes": {
            "merchant_code": "string (format: M{id:05d})",
            "event_ts": "string (ISO 8601 with timezone)",
            "revenue_cents": "int64 (original * 100)",
            "cost_cents": "int64 (original * 100)",
        },
    }
    if is_public:
        (step3_data_dir / "schema_mapping.json").write_text(
            json.dumps(schema_mapping, indent=2) + "\n"
        )

    # Classify rows
    # Build merchant_code lookup set for faster classification
    merchant_codes = set(merchants_df["merchant_code"].values)
    inactive_codes = set(
        merchants_df[~merchants_df["is_active"]]["merchant_code"].values
    )

    quarantine_rows = []
    valid_rows = []
    for idx, row in df_v2_with_bad.iterrows():
        error = classify_quarantine(row, merchants_df)
        if error is not None:
            qrow = row.to_dict()
            qrow["error_code"] = error
            quarantine_rows.append(qrow)
        else:
            valid_rows.append(row)

    quarantine_df = pd.DataFrame(quarantine_rows)
    valid_v2_df = pd.DataFrame(valid_rows)

    # Convert valid v2 rows to v1 format
    valid_v1_df = convert_v2_to_v1(valid_v2_df, merchants_df)

    # Build expected outputs
    step3_expected_dir.mkdir(parents=True, exist_ok=True)

    # Enriched transactions
    enriched = build_enriched_transactions(
        valid_v1_df, merchants_df, categories_df
    )
    enriched.to_parquet(
        step3_expected_dir / "enriched_transactions.parquet", index=False
    )

    # Quarantine
    quarantine_out = quarantine_df[
        list(df_v2_with_bad.columns) + ["error_code"]
    ].copy()
    quarantine_out = quarantine_out.sort_values("row_id").reset_index(
        drop=True
    )
    quarantine_out.to_parquet(
        step3_expected_dir / "quarantine.parquet", index=False
    )

    # Quality v2
    quality = build_quality_v2(
        df_v2_with_bad, quarantine_out, enriched, valid_v1_df
    )
    (step3_expected_dir / "quality_v2.json").write_text(
        json.dumps(quality, sort_keys=True, separators=(",", ":")) + "\n"
    )

    print(f"  input_v2: {len(df_v2_with_bad)} rows")
    print(f"  quarantine: {len(quarantine_out)} rows")
    print(f"  enriched: {len(enriched)} rows")
    print(f"  quarantine by error: {quarantine_out['error_code'].value_counts().to_dict()}")


def main() -> None:
    # Collect all merchant_ids from both datasets
    pub_v1 = pd.read_parquet(
        TASK_DIR / "steps/step_1/files/public_data/input.parquet"
    )
    hid_v1 = pd.read_parquet(
        TASK_DIR / "steps/step_1/hidden/hidden_data/input.parquet"
    )
    all_merchant_ids = set(pub_v1["merchant_id"].unique()) | set(
        hid_v1["merchant_id"].unique()
    )

    # Generate reference tables
    merchants_df = generate_merchants_table(all_merchant_ids)
    categories_df = generate_categories_table()

    print(f"Merchants table: {len(merchants_df)} rows, "
          f"{(~merchants_df['is_active']).sum()} inactive")

    datasets = {
        "public": {
            "v1_input": TASK_DIR
            / "steps/step_1/files/public_data/input.parquet",
            "data_dir": TASK_DIR / "steps/step_3/files/public_data",
            "expected_dir": TASK_DIR
            / "steps/step_3/files/public_data/expected",
        },
        "hidden": {
            "v1_input": TASK_DIR
            / "steps/step_1/hidden/hidden_data/input.parquet",
            "data_dir": TASK_DIR / "steps/step_3/hidden/hidden_data",
            "expected_dir": TASK_DIR
            / "steps/step_3/hidden/hidden_data/expected",
        },
    }

    for label, paths in datasets.items():
        print(f"\n{label}:")
        process_dataset(
            paths["v1_input"],
            paths["data_dir"],
            paths["expected_dir"],
            merchants_df,
            categories_df,
            is_public=(label == "public"),
        )
        # Print hashes
        for d in [paths["data_dir"], paths["expected_dir"]]:
            for f in sorted(d.glob("*.parquet")) + sorted(d.glob("*.json")):
                print(f"  {f.name} SHA256: {_sha256(f)}")


if __name__ == "__main__":
    main()
