"""Step 2: Advanced Analytics — pandas reference implementation.

READ-ONLY. Shows how the pandas pipeline produces merchant_analytics.parquet
and country_summary.parquet. Translate this logic to Polars in
/app/step_1/files/pipeline_polars.py.

Run (for reference only):
    python3 pipeline_pandas_advanced.py --in <input_dir> --out <output_dir>
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_dir", required=True)
    p.add_argument("--out", dest="out_dir", required=True)
    return p.parse_args()


# ── _ensure_columns (same as Step 1 — included for context) ───────────────


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


# ── Step 2: Merchant Analytics (window functions) ─────────────────────────


def build_merchant_analytics(df: pd.DataFrame) -> pd.DataFrame:
    """Per-transaction enrichment with window functions.

    Input:  DataFrame after _ensure_columns(), filtered to has_answer == 1.
    Output: DataFrame sorted by [merchant_id, event_date, row_id].
    """
    df = df[df["has_answer"] == 1].copy()
    df = df.sort_values(["merchant_id", "event_date", "row_id"]).reset_index(drop=True)

    # ── 1. Rolling 30-day revenue per merchant ──────────────────────────
    #   Pandas: groupby → set datetime index → rolling('30D') → sum()
    #   Window is right-closed: (t - 30D, t] — includes current row.
    df["rolling_30d_revenue"] = (
        df.groupby("merchant_id")
        .apply(
            lambda g: g.set_index("event_date")["revenue"]
            .rolling("30D")
            .sum()
            .reset_index(level=0, drop=True)
        )
        .droplevel(0)
        .sort_index()
        .values
    )

    # ── 2. Dense rank of revenue within (country, tier), descending ─────
    df["revenue_rank"] = (
        df.groupby(["country", "tier"])["revenue"]
        .rank(method="dense", ascending=False)
        .astype("int64")
    )

    # ── 3. QA percentile band within (country, tier) ───────────────────
    #   percent_rank → cut into quartiles Q1–Q4
    #   Q1 = lowest 25%, Q4 = highest 25%
    prank = df.groupby(["country", "tier"])["qa_score"].transform(
        lambda s: s.rank(pct=True, method="average")
    )
    df["qa_percentile_band"] = pd.cut(
        prank,
        bins=[0, 0.25, 0.5, 0.75, 1.0],
        labels=["Q1", "Q2", "Q3", "Q4"],
        include_lowest=True,
    ).astype(str)

    # ── 4. Z-score of revenue within merchant + anomaly flag ───────────
    #   WARNING: merchants with a single transaction have std() == NaN
    #   (ddof=1). Must fill NaN z-scores with 0.0.
    merchant_mean = df.groupby("merchant_id")["revenue"].transform("mean")
    merchant_std = df.groupby("merchant_id")["revenue"].transform("std")
    df["z_score"] = (df["revenue"] - merchant_mean) / merchant_std
    df["z_score"] = df["z_score"].fillna(0.0)
    df["is_anomaly"] = (df["z_score"].abs() > 2).astype("int8")

    # ── 5. Cumulative revenue within (merchant_id, event_month) ────────
    df["monthly_cumulative_revenue"] = df.groupby(
        ["merchant_id", "event_month"]
    )["revenue"].cumsum()

    # ── 6. Month-over-month revenue growth ─────────────────────────────
    #   Aggregate monthly → shift → compute growth → join back.
    #   First month per merchant has NaN (no previous month).
    monthly = (
        df.groupby(["merchant_id", "event_month"], as_index=False)["revenue"]
        .sum()
        .rename(columns={"revenue": "monthly_revenue"})
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
        on=["merchant_id", "event_month"],
        how="left",
    )

    # ── Select & round ─────────────────────────────────────────────────
    output_cols = [
        "row_id", "merchant_id", "country", "tier",
        "event_date", "event_month", "revenue", "cost", "qa_score",
        "rolling_30d_revenue", "revenue_rank", "qa_percentile_band",
        "z_score", "is_anomaly",
        "monthly_cumulative_revenue", "mom_revenue_growth",
    ]
    result = df[output_cols].copy()
    for col in result.select_dtypes(include=["float64"]).columns:
        result[col] = result[col].round(6)
    result = result.sort_values(["merchant_id", "event_date", "row_id"]).reset_index(drop=True)
    return result


# ── Step 2: Country Summary (concentration metrics) ───────────────────────


def build_country_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-country concentration and distribution metrics.

    Input:  DataFrame after _ensure_columns(), filtered to has_answer == 1.
    Output: One row per country, sorted by [country].
    """
    df = df[df["has_answer"] == 1].copy()

    # Revenue per merchant per country
    merchant_rev = df.groupby(["country", "merchant_id"], as_index=False)["revenue"].sum()

    # ── HHI (Herfindahl-Hirschman Index) ──────────────────────────────
    country_total = merchant_rev.groupby("country")["revenue"].transform("sum")
    merchant_rev["_share"] = merchant_rev["revenue"] / country_total
    hhi = (
        merchant_rev.groupby("country")["_share"]
        .apply(lambda s: (s**2).sum())
        .reset_index(name="hhi")
    )

    # ── Top-3 merchant share ──────────────────────────────────────────
    top3 = (
        merchant_rev.groupby("country")
        .apply(lambda g: g.nlargest(3, "revenue")["revenue"].sum() / g["revenue"].sum())
        .reset_index(name="top3_share")
    )

    # ── Merchant count ────────────────────────────────────────────────
    mc = (
        merchant_rev.groupby("country")["merchant_id"]
        .nunique()
        .reset_index(name="merchant_count")
    )

    # ── Gini coefficient ──────────────────────────────────────────────
    def _gini(group: pd.DataFrame) -> float:
        revs = np.sort(group["revenue"].values)
        n = len(revs)
        if n <= 1:
            return 0.0
        total = revs.sum()
        if total == 0:
            return 0.0
        idx = np.arange(1, n + 1)
        return float((2.0 * (idx * revs).sum()) / (n * total) - (n + 1) / n)

    gini = (
        merchant_rev.groupby("country")
        .apply(_gini)
        .reset_index(name="gini_coefficient")
    )

    # ── Median merchant revenue ───────────────────────────────────────
    med = (
        merchant_rev.groupby("country")["revenue"]
        .median()
        .reset_index(name="median_merchant_revenue")
    )

    # ── Premium share ─────────────────────────────────────────────────
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
    ps = total_rev.merge(premium_rev, on="country", how="left")
    ps["premium_revenue"] = ps["premium_revenue"].fillna(0.0)
    ps["premium_share"] = ps["premium_revenue"] / ps["total_revenue"]

    # ── Combine ───────────────────────────────────────────────────────
    result = hhi
    for other in [top3, mc, gini, med]:
        result = result.merge(other, on="country")
    result = result.merge(ps[["country", "premium_share"]], on="country")

    result = result[[
        "country", "hhi", "top3_share", "merchant_count",
        "gini_coefficient", "median_merchant_revenue", "premium_share",
    ]]
    for col in result.select_dtypes(include=["float64"]).columns:
        result[col] = result[col].round(6)
    result = result.sort_values("country").reset_index(drop=True)
    return result


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()
    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(in_dir / "input.parquet")
    df = _ensure_columns(df)

    analytics = build_merchant_analytics(df)
    analytics.to_parquet(out_dir / "merchant_analytics.parquet", index=False)

    summary = build_country_summary(df)
    summary.to_parquet(out_dir / "country_summary.parquet", index=False)


if __name__ == "__main__":
    main()
