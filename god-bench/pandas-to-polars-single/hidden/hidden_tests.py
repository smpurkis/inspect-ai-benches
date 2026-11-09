"""Generated and metamorphic verification for compact v2 normalization."""

from __future__ import annotations

import ast
import random
import sys
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal

FILES = Path(__file__).resolve().parents[1] / "files"
sys.path.insert(0, str(FILES))
from normalization import NORMALIZED_COLUMNS, normalize_and_quarantine  # noqa: E402


def _merchants() -> pl.LazyFrame:
    return pl.DataFrame({
        "merchant_code": ["A", "B", "OFF"], "merchant_id": [10, 20, 30],
        "tier": ["premium", "basic", "basic"], "segment": ["x", "y", "z"],
        "onboarding_date": ["2020-01-01"] * 3, "is_active": [True, True, False],
    }).lazy()


def _row(index: int, **changes) -> dict:
    return {
        "row_id": index, "merchant_code": "A", "country": "US",
        "event_ts": "2024-01-01T00:00:00Z", "revenue_cents": 100,
        "cost_cents": 40, "currency": "USD", "channel": "api",
        "question": "q", "context": "c", "title": "t", "answer": "a",
    } | changes


def _run(rows):
    valid, bad = normalize_and_quarantine(pl.DataFrame(rows).lazy(), _merchants())
    assert isinstance(valid, pl.LazyFrame) and isinstance(bad, pl.LazyFrame)
    return valid.collect(), bad.collect()


def test_kernel_has_no_eager_io_or_collection() -> None:
    tree = ast.parse((FILES / "normalization.py").read_text(encoding="utf-8"))
    forbidden = {"collect", "read_parquet", "read_csv", "to_pandas", "write_parquet"}
    calls = {node.func.attr for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not calls & forbidden


@pytest.mark.parametrize("seed", range(8))
def test_generated_priority_partition_schema_and_oracle(seed: int) -> None:
    rng = random.Random(seed)
    rows, expected = [], []
    codes = [None, "NULL_REQUIRED", "INVALID_DATE", "NEGATIVE_AMOUNT",
             "MISSING_MERCHANT", "INACTIVE_MERCHANT"]
    for index in range(1, 81):
        code = rng.choice(codes)
        row = _row(index, merchant_code=rng.choice(["A", "B"]))
        if code == "NULL_REQUIRED":
            row.update(merchant_code=rng.choice([None, "", "  "]), event_ts="bad",
                       revenue_cents=-5)
        elif code == "INVALID_DATE":
            row.update(event_ts=rng.choice([None, "", "nonsense", "2023-12-31T23:00:00Z"]),
                       revenue_cents=-5)
        elif code == "NEGATIVE_AMOUNT":
            row[rng.choice(["revenue_cents", "cost_cents"])] = -1
        elif code == "MISSING_MERCHANT":
            row["merchant_code"] = "UNKNOWN"
        elif code == "INACTIVE_MERCHANT":
            row["merchant_code"] = "OFF"
        rows.append(row)
        if code:
            expected.append((index, code))
    valid, bad = _run(rows)
    assert valid.columns == NORMALIZED_COLUMNS
    assert bad.columns == list(rows[0]) + ["error_code"]
    assert bad.select("row_id", "error_code").rows() == expected
    assert valid.height + bad.height == len(rows)


def test_generated_offsets_dst_and_optional_nulls() -> None:
    rows = [
        _row(1, event_ts="2024-03-10T01:30:00-05:00", context=None),
        _row(2, event_ts="2024-03-10T03:30:00-04:00", answer=None),
        _row(3, event_ts="2024-11-03T01:30:00-05:00"),
    ]
    valid, bad = _run(rows)
    assert bad.is_empty()
    assert valid["event_date"].dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_list() == [
        "2024-03-10T06:30:00Z", "2024-03-10T07:30:00Z", "2024-11-03T06:30:00Z"
    ]
    assert valid.select("context", "answer").rows()[:2] == [(None, "a"), ("c", None)]


def test_join_values_and_quarantine_preserves_original_rows_and_dtypes() -> None:
    rows = [
        _row(4, merchant_code="A", country="CA", revenue_cents=411, context=None),
        _row(1, merchant_code="B", country="GB", revenue_cents=122, answer=None),
        _row(3, merchant_code="OFF", country="DE", revenue_cents=333,
             currency="EUR", question="inactive-original"),
        _row(2, merchant_code="UNKNOWN", country="JP", revenue_cents=244,
             cost_cents=17, channel="mobile", title="missing-original"),
    ]
    source = pl.DataFrame(rows).with_columns(
        pl.col("row_id").cast(pl.UInt32),
        pl.col("revenue_cents").cast(pl.Int32),
        pl.col("cost_cents").cast(pl.Int16),
    )
    valid_lazy, bad_lazy = normalize_and_quarantine(source.lazy(), _merchants())
    valid, bad = valid_lazy.collect(), bad_lazy.collect()

    assert valid.select("row_id", "merchant_id", "tier", "segment").rows() == [
        (4, 10, "premium", "x"),
        (1, 20, "basic", "y"),
    ]
    expected_bad = source.filter(pl.col("row_id").is_in([2, 3])).sort("row_id").with_columns(
        pl.Series(
            "error_code", ["MISSING_MERCHANT", "INACTIVE_MERCHANT"], dtype=pl.String
        )
    )
    assert_frame_equal(bad, expected_bad)
    assert bad.select(source.columns).schema == source.schema


def test_metamorphic_permutation_and_cent_scaling() -> None:
    rows = [_row(i, merchant_code="A" if i % 2 else "B",
                 revenue_cents=i * 137, cost_cents=i * 11) for i in range(1, 30)]
    baseline = _run(rows)
    shuffled = list(rows)
    random.Random(90210).shuffle(shuffled)
    permuted = _run(shuffled)
    assert_frame_equal(baseline[0], permuted[0])
    assert_frame_equal(baseline[1], permuted[1])
    scaled, _ = _run([dict(row, revenue_cents=row["revenue_cents"] * 3) for row in rows])
    assert scaled["revenue"].to_list() == pytest.approx(
        [value * 3 for value in baseline[0]["revenue"]], abs=1e-12
    )


def test_single_field_mutations_change_only_expected_classification() -> None:
    base = _row(1)
    cases = [
        ({"country": ""}, "NULL_REQUIRED"), ({"event_ts": "bad"}, "INVALID_DATE"),
        ({"cost_cents": -1}, "NEGATIVE_AMOUNT"),
        ({"merchant_code": "UNKNOWN"}, "MISSING_MERCHANT"),
        ({"merchant_code": "OFF"}, "INACTIVE_MERCHANT"),
    ]
    for mutation, code in cases:
        valid, bad = _run([base | mutation])
        assert valid.is_empty() and bad["error_code"].to_list() == [code]
