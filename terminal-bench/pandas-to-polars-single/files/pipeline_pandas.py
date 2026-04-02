import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_dir", required=True)
    parser.add_argument("--out", dest="out_dir", required=True)
    return parser.parse_args()


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


def _build_outputs(df: pd.DataFrame, out_dir: Path) -> None:
    df = df[df["has_answer"] == 1].copy()

    summary = (
        df.groupby(["country", "tier", "event_month", "context_bucket"], as_index=False)
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

    summary[["avg_revenue", "avg_margin_pct", "p90_qa_score", "profit_rate"]] = summary[
        ["avg_revenue", "avg_margin_pct", "p90_qa_score", "profit_rate"]
    ].round(6)

    summary.to_parquet(out_dir / "summary.parquet", index=False)

    merchants = (
        df.groupby(["country", "merchant_id"], as_index=False)
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
        .loc[
            :,
            [
                "country",
                "merchant_id",
                "merchant_revenue",
                "merchant_margin",
                "merchant_avg_qa",
            ],
        ]
        .sort_values(["country", "merchant_revenue", "merchant_id"], ascending=[True, False, True])
        .reset_index(drop=True)
    )

    top_merchants[["merchant_revenue", "merchant_margin", "merchant_avg_qa"]] = top_merchants[
        ["merchant_revenue", "merchant_margin", "merchant_avg_qa"]
    ].round(6)

    top_merchants.to_csv(out_dir / "top_merchants.csv", index=False, float_format="%.6f")

    counts = df["country"].value_counts()
    max_count = counts.max()
    top_country = sorted(counts[counts == max_count].index.tolist())[0]

    max_event = df["event_date"].max()
    run_id = max_event.strftime("%Y%m%d-000000")

    quality = {
        "row_count": int(len(df)),
        "distinct_merchants": int(df["merchant_id"].nunique()),
        "mean_qa_score": round(float(df["qa_score"].mean()), 6),
        "pct_premium": round(float(df["is_premium"].mean()), 6),
        "top_country": top_country,
        "run_id": run_id,
    }

    (out_dir / "quality.json").write_text(
        json.dumps(quality, sort_keys=True, separators=(",", ":")) + "\n"
    )


def _build_dataset(source: pd.DataFrame, out_dir: Path) -> None:
    rng = np.random.default_rng(20260218)
    idx = rng.integers(0, len(source), size=1_000_000)
    df = source.iloc[idx].reset_index(drop=True)

    rename_map = {
        "id": "doc_id",
        "question_id": "question_id",
        "qa_id": "qa_id",
        "question": "question",
        "context": "context",
        "title": "title",
        "answers": "answer",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    if "doc_id" not in df.columns:
        df["doc_id"] = rng.integers(1, 10_000_000, size=len(df))
    if "question_id" not in df.columns:
        df["question_id"] = np.arange(1, len(df) + 1, dtype="int64")
    if "qa_id" not in df.columns:
        df["qa_id"] = rng.integers(1, 5_000_000, size=len(df))

    if "question" not in df.columns or "context" not in df.columns:
        raise ValueError("Source dataset must include question and context columns")
    if "title" not in df.columns:
        df["title"] = ""
    if "answer" not in df.columns:
        df["answer"] = ""

    df["row_id"] = np.arange(1, len(df) + 1, dtype="int64")

    if "answer" in df.columns:
        def _normalize_answer(value: object) -> str:
            if isinstance(value, dict):
                text = value.get("text", "")
                if isinstance(text, list):
                    return str(text[0]) if text else ""
                return str(text)
            if isinstance(value, list):
                return str(value[0]) if value else ""
            return "" if value is None else str(value)

        df["answer"] = df["answer"].map(_normalize_answer).astype("string")
    df["answer"] = df["answer"].str.split("\n").str[0]

    df["merchant_id"] = (df["doc_id"] * 17 + df["qa_id"] * 13 + df["row_id"]) % 5000
    df["merchant_id"] = df["merchant_id"].astype("int64")

    countries = np.array(["US", "GB", "DE", "FR", "CA", "IN", "AU", "JP"])
    df["country"] = countries[df["merchant_id"] % len(countries)]

    base_date = pd.Timestamp("2024-01-01", tz="UTC")
    df["event_date"] = base_date + pd.to_timedelta(df["row_id"] % 365, unit="D")

    df["revenue"] = (df["context"].str.len().fillna(0) * 0.05 + (df["qa_id"] % 50)).astype(
        "float64"
    )
    df["cost"] = (df["question"].str.len().fillna(0) * 0.03 + (df["qa_id"] % 20)).astype(
        "float64"
    )

    df["tier"] = np.where(df["merchant_id"] % 5 == 0, "premium", "standard")

    df = _ensure_columns(df)

    ordered_cols = [
        "row_id",
        "doc_id",
        "question_id",
        "qa_id",
        "question",
        "context",
        "title",
        "answer",
        "answer_length",
        "question_length",
        "context_length",
        "title_length",
        "question_tokens",
        "context_tokens",
        "answer_tokens",
        "title_tokens",
        "has_answer",
        "is_long_context",
        "context_bucket",
        "question_bucket",
        "merchant_id",
        "country",
        "event_date",
        "event_month",
        "revenue",
        "cost",
        "margin",
        "margin_pct",
        "is_premium",
        "tier",
    ]

    df = df[ordered_cols]
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_dir / "input.parquet", index=False)


def main() -> None:
    args = parse_args()
    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = in_dir / "input.parquet"
    if not input_path.exists():
        offline_source = Path(__file__).parent / "task-deps" / "source.parquet"
        if offline_source.exists():
            source = pd.read_parquet(offline_source)
        else:
            source = pd.read_parquet(
                "https://huggingface.co/datasets/ibm/duorc/resolve/refs/convert/parquet/ParaphraseRC/train/0000.parquet"
            )
        _build_dataset(source, in_dir)

    df = pd.read_parquet(input_path)
    df = _ensure_columns(df)
    _build_outputs(df, out_dir)


if __name__ == "__main__":
    main()
