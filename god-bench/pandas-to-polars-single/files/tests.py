"""Public normal, edge, invariant, and determinism tests for the kernel."""

from __future__ import annotations

import polars as pl
from polars.testing import assert_frame_equal

from normalization import NORMALIZED_COLUMNS, normalize_and_quarantine


def _frames(rows: list[dict]) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    defaults = {
        "row_id": 1, "merchant_code": "M1", "country": "US",
        "event_ts": "2024-03-10T01:30:00-05:00", "revenue_cents": 1250,
        "cost_cents": 250, "currency": "USD", "channel": "web",
        "question": "q", "context": "context", "title": "title", "answer": "yes",
    }
    source = pl.DataFrame([defaults | row for row in rows])
    merchants = pl.DataFrame({
        "merchant_code": ["M1", "OFF"], "merchant_id": [7, 8],
        "tier": ["premium", "basic"], "segment": ["retail", "retail"],
        "onboarding_date": ["2020-01-01", "2020-01-01"],
        "is_active": [True, False],
    })
    return source.lazy(), merchants.lazy()


def _run(rows: list[dict]) -> tuple[pl.DataFrame, pl.DataFrame]:
    source, merchants = _frames(rows)
    valid, bad = normalize_and_quarantine(source, merchants)
    return valid.collect(), bad.collect()


def test_normal_offset_timestamp_and_exact_schema() -> None:
    valid, bad = _run([{}])
    assert bad.is_empty()
    assert valid.columns == NORMALIZED_COLUMNS
    assert valid["event_date"].dt.strftime("%Y-%m-%dT%H:%M:%SZ").item() == "2024-03-10T06:30:00Z"
    assert valid.select("revenue", "cost").row(0) == (12.5, 2.5)


def test_edge_first_error_wins_and_optional_nulls_survive() -> None:
    valid, bad = _run([
        {"row_id": 2, "merchant_code": " ", "event_ts": "bad", "revenue_cents": -1},
        {"row_id": 3, "context": None, "answer": None},
        {"row_id": 4, "merchant_code": "OFF"},
    ])
    assert bad.select("row_id", "error_code").rows() == [
        (2, "NULL_REQUIRED"), (4, "INACTIVE_MERCHANT")
    ]
    assert valid.select("row_id", "context", "answer").rows() == [(3, None, None)]


def test_partition_invariant_preserves_each_input_row_once() -> None:
    valid, bad = _run([{}, {"row_id": 2, "event_ts": "2023-12-31T23:00:00Z"},
                       {"row_id": 3, "merchant_code": "missing"}])
    assert sorted(valid["row_id"].to_list() + bad["row_id"].to_list()) == [1, 2, 3]


def test_deterministic_under_source_permutation() -> None:
    rows = [{"row_id": 2}, {"row_id": 1}, {"row_id": 3, "merchant_code": "missing"}]
    first = _run(rows)
    second = _run(list(reversed(rows)))
    for left, right in zip(first, second):
        assert_frame_equal(left, right)
