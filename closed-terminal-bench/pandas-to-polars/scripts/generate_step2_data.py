#!/usr/bin/env python3
"""Generate expected outputs for pandas-to-polars Step 2.

Reads step 1's public and hidden input.parquet files, applies _ensure_columns(),
computes window-function analytics (merchant_analytics.parquet) and country
concentration metrics (country_summary.parquet), writes expected outputs, and
prints SHA256 hashes.

Usage:
    python3 scripts/generate_step2_data.py
"""

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

TASK_DIR = Path(__file__).resolve().parent.parent


# ── helpers copied verbatim from pipeline_pandas.py ────────────────────────


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

    df["question_tokens"] = (
        df["question"].str.findall(r"\S+").str.len().fillna(0).astype("int64")
    )
    df["context_tokens"] = (
        df["context"].str.findall(r"\S+").str.len().fillna(0).astype("int64")
    )
    df["answer_tokens"] = (
        df["answer"].str.findall(r"\S+").str.len().fillna(0).astype("int64")
    )
    df["title_tokens"] = (
        df["title"].str.findall(r"\S+").str.len().fillna(0).astype("int64")
    )

    df["has_answer"] = (df["answer_length"] > 0).astype("int8")
    df["is_long_context"] = (df["context_tokens"] >= 360).astype("int8")

    df["context_bucket"] = _bucketize(df["context_tokens"], 120, 360)
    df["question_bucket"] = _bucketize(df["question_tokens"], 12, 22)

    df["event_month"] = df["event_date"].dt.strftime("%Y-%m")

    df["margin"] = df["revenue"] - df["cost"]
    df["margin_pct"] = np.where(
        df["revenue"] != 0, df["margin"] / df["revenue"], 0.0
    )

    df["net_revenue"] = df["revenue"] - df["cost"]
    df["profit_flag"] = (df["net_revenue"] >= 25).astype("int8")

    df["qa_score"] = (
        (df["question_tokens"] * 1.3 + df["answer_tokens"] * 2.1)
        / (df["context_tokens"] + 10)
    ).astype("float64")

    df["is_premium"] = (df["tier"] == "premium").astype("int8")

    return df


# ── Step 2 analytics ──────────────────────────────────────────────────────


def build_merchant_analytics(df: pd.DataFrame) -> pd.DataFrame:
    """Per-transaction enrichment with window functions."""
    df = df[df["has_answer"] == 1].copy()
    df = df.sort_values(["merchant_id", "event_date", "row_id"]).reset_index(
        drop=True
    )

    # 1. Rolling 30-day revenue per merchant
    parts = []
    for _, group in df.groupby("merchant_id"):
        g = group.set_index("event_date")
        g["rolling_30d_revenue"] = g["revenue"].rolling("30D").sum()
        parts.append(g.reset_index())
    df = pd.concat(parts, ignore_index=True)
    df = df.sort_values(["merchant_id", "event_date", "row_id"]).reset_index(
        drop=True
    )

    # 2. Dense rank of revenue within (country, tier), descending
    df["revenue_rank"] = (
        df.groupby(["country", "tier"])["revenue"]
        .rank(method="dense", ascending=False)
        .astype("int64")
    )

    # 3. QA percentile band within (country, tier)
    prank = df.groupby(["country", "tier"])["qa_score"].rank(
        pct=True, method="average"
    )
    df["qa_percentile_band"] = pd.cut(
        prank,
        bins=[0, 0.25, 0.5, 0.75, 1.0],
        labels=["Q1", "Q2", "Q3", "Q4"],
        include_lowest=True,
    ).astype(str)

    # 4. Z-score of revenue within merchant + anomaly flag
    grp = df.groupby("merchant_id")
    merchant_mean = grp["revenue"].transform("mean")
    merchant_std = grp["revenue"].transform("std")  # ddof=1 → NaN for n=1
    df["z_score"] = (df["revenue"] - merchant_mean) / merchant_std
    df["z_score"] = df["z_score"].fillna(0.0)
    df["is_anomaly"] = (df["z_score"].abs() > 2).astype("int8")

    # 5. Cumulative revenue within (merchant, month)
    df["monthly_cumulative_revenue"] = df.groupby(
        ["merchant_id", "event_month"]
    )["revenue"].cumsum()

    # 6. Month-over-month revenue growth
    monthly = (
        df.groupby(["merchant_id", "event_month"], as_index=False)["revenue"]
        .sum()
        .rename(columns={"revenue": "monthly_revenue"})
    )
    monthly = monthly.sort_values(["merchant_id", "event_month"]).reset_index(
        drop=True
    )
    monthly["prev_monthly_revenue"] = monthly.groupby("merchant_id")[
        "monthly_revenue"
    ].shift(1)
    monthly["mom_revenue_growth"] = (
        monthly["monthly_revenue"] - monthly["prev_monthly_revenue"]
    ) / monthly["prev_monthly_revenue"]

    df = df.merge(
        monthly[["merchant_id", "event_month", "mom_revenue_growth"]],
        on=["merchant_id", "event_month"],
        how="left",
    )

    # Select output columns
    output_cols = [
        "row_id",
        "merchant_id",
        "country",
        "tier",
        "event_date",
        "event_month",
        "revenue",
        "cost",
        "qa_score",
        "rolling_30d_revenue",
        "revenue_rank",
        "qa_percentile_band",
        "z_score",
        "is_anomaly",
        "monthly_cumulative_revenue",
        "mom_revenue_growth",
    ]
    result = df[output_cols].copy()

    # Round float columns to 6 dp
    for col in result.select_dtypes(include=["float64"]).columns:
        result[col] = result[col].round(6)

    # Sort
    result = result.sort_values(
        ["merchant_id", "event_date", "row_id"]
    ).reset_index(drop=True)

    return result


def build_country_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-country concentration metrics."""
    df = df[df["has_answer"] == 1].copy()

    # Revenue per merchant per country
    merchant_rev = df.groupby(
        ["country", "merchant_id"], as_index=False
    )["revenue"].sum()

    # HHI (Herfindahl-Hirschman Index)
    rows = []
    for country, group in merchant_rev.groupby("country"):
        total = group["revenue"].sum()
        shares = group["revenue"] / total
        rows.append({"country": country, "hhi": float((shares**2).sum())})
    hhi_df = pd.DataFrame(rows)

    # Top-3 merchant share
    rows = []
    for country, group in merchant_rev.groupby("country"):
        total = group["revenue"].sum()
        top3 = group.nlargest(3, "revenue")["revenue"].sum()
        rows.append(
            {"country": country, "top3_share": top3 / total if total else 0.0}
        )
    top3_df = pd.DataFrame(rows)

    # Merchant count
    mc_df = (
        merchant_rev.groupby("country")["merchant_id"]
        .nunique()
        .reset_index()
        .rename(columns={"merchant_id": "merchant_count"})
    )

    # Gini coefficient
    def _gini(revs: np.ndarray) -> float:
        revs = np.sort(revs)
        n = len(revs)
        if n <= 1:
            return 0.0
        total = revs.sum()
        if total == 0:
            return 0.0
        idx = np.arange(1, n + 1)
        return float((2.0 * (idx * revs).sum()) / (n * total) - (n + 1) / n)

    rows = []
    for country, group in merchant_rev.groupby("country"):
        rows.append(
            {
                "country": country,
                "gini_coefficient": _gini(group["revenue"].values),
            }
        )
    gini_df = pd.DataFrame(rows)

    # Median merchant revenue
    med_df = (
        merchant_rev.groupby("country")["revenue"]
        .median()
        .reset_index()
        .rename(columns={"revenue": "median_merchant_revenue"})
    )

    # Premium share
    premium_rev = (
        df[df["tier"] == "premium"]
        .groupby("country", as_index=False)["revenue"]
        .sum()
        .rename(columns={"revenue": "premium_revenue"})
    )
    total_rev = (
        df.groupby("country", as_index=False)["revenue"]
        .sum()
        .rename(columns={"revenue": "total_revenue"})
    )
    ps_df = total_rev.merge(premium_rev, on="country", how="left")
    ps_df["premium_revenue"] = ps_df["premium_revenue"].fillna(0.0)
    ps_df["premium_share"] = ps_df["premium_revenue"] / ps_df["total_revenue"]

    # Combine
    result = hhi_df
    for other in [top3_df, mc_df, gini_df, med_df]:
        result = result.merge(other, on="country")
    result = result.merge(ps_df[["country", "premium_share"]], on="country")

    result = result[
        [
            "country",
            "hhi",
            "top3_share",
            "merchant_count",
            "gini_coefficient",
            "median_merchant_revenue",
            "premium_share",
        ]
    ]

    for col in result.select_dtypes(include=["float64"]).columns:
        result[col] = result[col].round(6)

    result = result.sort_values("country").reset_index(drop=True)
    return result


# ── Main ──────────────────────────────────────────────────────────────────


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def process_dataset(input_path: Path, expected_dir: Path) -> None:
    df = pd.read_parquet(input_path)
    df = _ensure_columns(df)

    expected_dir.mkdir(parents=True, exist_ok=True)

    analytics = build_merchant_analytics(df)
    analytics.to_parquet(expected_dir / "merchant_analytics.parquet", index=False)

    summary = build_country_summary(df)
    summary.to_parquet(expected_dir / "country_summary.parquet", index=False)

    print(f"  merchant_analytics: {len(analytics)} rows, {len(analytics.columns)} cols")
    print(f"  country_summary: {len(summary)} rows, {len(summary.columns)} cols")


def main() -> None:
    datasets = {
        "public": {
            "input": TASK_DIR / "steps/step_1/files/public_data/input.parquet",
            "expected": TASK_DIR / "steps/step_2/files/public_data/expected",
        },
        "hidden": {
            "input": TASK_DIR / "steps/step_1/hidden/hidden_data/input.parquet",
            "expected": TASK_DIR / "steps/step_2/hidden/hidden_data/expected",
        },
    }

    for label, paths in datasets.items():
        print(f"\n{label}:")
        process_dataset(paths["input"], paths["expected"])
        for name in ("merchant_analytics.parquet", "country_summary.parquet"):
            p = paths["expected"] / name
            print(f"  {name} SHA256: {_sha256(p)}")


if __name__ == "__main__":
    main()
