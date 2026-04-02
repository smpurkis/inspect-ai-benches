# pandas-to-polars: Full Pipeline Migration

Migrate a pandas ETL pipeline to Polars. Implement `/app/files/pipeline_polars.py`
to handle core aggregations, window functions, schema evolution, lazy execution,
and data quarantine in one pipeline.

## Resources

- Pandas reference implementations (read-only):
  - `/app/files/pipeline_pandas.py` (core aggregation logic)
  - `/app/files/pipeline_pandas_advanced.py` (window function logic)
  - `/app/files/pipeline_pandas_v2.py` (schema evolution + quarantine logic)
- V1 public input: `/app/files/public_data/input.parquet`
- V2 public input: `/app/files/public_data/input_v2.parquet`
- Reference tables: `/app/files/public_data/merchants.parquet`,
  `/app/files/public_data/categories.parquet`
- Schema mapping: `/app/files/public_data/schema_mapping.json`
- Expected outputs: `/app/files/public_data/expected/`

## CLI contract

```
python3 /app/files/pipeline_polars.py --in <input_dir> --out <output_dir>
```

## Schema Detection

- If `input_v2.parquet` exists in `--in` dir, use **v2 mode**
- Otherwise `input.parquet`, use **v1 mode** (produces core + analytics outputs only)

---

## Derived Column Formulas

These formulas apply to both v1 and v2 code paths. The input parquet already
contains text fields (`question`, `context`, `title`, `answer`) and their
derived length/token columns.

### Text bucketing

- `context_bucket`: `"short"` if `context_tokens < 120`, `"medium"` if `context_tokens < 360`, else `"long"`
- `question_bucket`: `"short"` if `question_tokens < 12`, `"medium"` if `question_tokens < 22`, else `"long"`

### Computed columns

| Column | Formula |
|--------|---------|
| `margin` | `revenue - cost` |
| `margin_pct` | `margin / revenue` (0.0 if `revenue == 0`) |
| `net_revenue` | `revenue - cost` |
| `profit_flag` | 1 if `net_revenue >= 25`, else 0 |
| `qa_score` | `(question_tokens * 1.3 + answer_tokens * 2.1) / (context_tokens + 10)` |
| `is_premium` | 1 if `tier == "premium"`, else 0 |
| `has_answer` | 1 if `answer_length > 0`, else 0 |
| `event_month` | `event_date` formatted as `"YYYY-MM"` |

### Window / analytics columns

All window columns are computed on rows where `has_answer == 1`, sorted by
`[merchant_id, event_date, row_id]`.

| Column | Formula |
|--------|---------|
| `rolling_30d_revenue` | 30-day rolling sum of `revenue` per `merchant_id`. Window is right-closed: `(t - 30D, t]` including the current row. |
| `revenue_rank` | Dense rank of `revenue` within `(country, tier)`, descending (rank 1 = highest revenue). |
| `qa_percentile_band` | Percent rank (average method) of `qa_score` within `(country, tier)`, then cut into quartile labels: `[0, 0.25] = "Q1"`, `(0.25, 0.5] = "Q2"`, `(0.5, 0.75] = "Q3"`, `(0.75, 1.0] = "Q4"`. Q1 = lowest 25%. |
| `z_score` | `(revenue - merchant_mean) / merchant_std` per `merchant_id` (std uses ddof=1). Merchants with a single transaction have std=NaN; fill NaN z-scores with 0.0. |
| `is_anomaly` | 1 if `abs(z_score) > 2`, else 0 |
| `monthly_cumulative_revenue` | Cumulative sum of `revenue` within `(merchant_id, event_month)`, in sort order. |
| `mom_revenue_growth` | Month-over-month revenue growth per merchant. Aggregate total monthly revenue per `(merchant_id, event_month)`, shift by 1 month, then compute `(current_month - prev_month) / prev_month`. First month per merchant is null (no previous month). Join back to each row by `(merchant_id, event_month)`. |

---

## V1 Mode Outputs

### 1. `summary.parquet`

Filter to `has_answer == 1`. Group by `[country, tier, event_month, context_bucket]`.

| Aggregation Column | Formula |
|--------------------|---------|
| `rows` | count of `row_id` |
| `avg_revenue` | mean of `revenue` |
| `avg_margin_pct` | mean of `margin_pct` |
| `p90_qa_score` | 90th percentile of `qa_score` (linear interpolation) |
| `profit_rate` | mean of `profit_flag` |

Sort: `[event_month, country, tier, context_bucket]`. Round all floats to 6 decimal places.

### 2. `top_merchants.csv`

Filter to `has_answer == 1`. Group by `[country, merchant_id]`.

| Aggregation Column | Formula |
|--------------------|---------|
| `merchant_rows` | count of `row_id` |
| `merchant_revenue` | sum of `revenue` |
| `merchant_margin` | sum of `margin` |
| `merchant_avg_qa` | mean of `qa_score` |

For each country, select the top 3 merchants by `merchant_revenue`.
Break ties by `merchant_margin` (desc), then `merchant_id` (asc).

Output columns: `country`, `merchant_id`, `merchant_revenue`, `merchant_margin`, `merchant_avg_qa`.
Sort: `[country asc, merchant_revenue desc, merchant_id asc]`. Round all floats to 6 decimal places.

### 3. `quality.json`

Compact JSON (no whitespace, sorted keys). Computed on `has_answer == 1` rows.

```json
{
  "distinct_merchants": <int, nunique merchant_id>,
  "mean_qa_score": <float, 6dp>,
  "pct_premium": <float, mean of is_premium, 6dp>,
  "row_count": <int, number of rows>,
  "run_id": "<YYYYMMDD-000000 from max event_date>",
  "top_country": "<country with highest row count, ties broken alphabetically>"
}
```

### 4. `merchant_analytics.parquet`

Per-transaction enrichment with window columns, on `has_answer == 1` rows.

Output columns (in order): `row_id`, `merchant_id`, `country`, `tier`,
`event_date`, `event_month`, `revenue`, `cost`, `qa_score`,
`rolling_30d_revenue`, `revenue_rank`, `qa_percentile_band`,
`z_score`, `is_anomaly`, `monthly_cumulative_revenue`, `mom_revenue_growth`.

Sort: `[merchant_id, event_date, row_id]`. Round all floats to 6 decimal places.

### 5. `country_summary.parquet`

One row per country. Concentration and distribution metrics computed on
`has_answer == 1` rows, using per-merchant revenue aggregates.

| Column | Formula |
|--------|---------|
| `hhi` | Herfindahl-Hirschman Index: sum of squared market shares per country. Market share = merchant_revenue / country_total_revenue. |
| `top3_share` | Sum of revenue of top 3 merchants / total country revenue. |
| `merchant_count` | Number of unique merchants per country. |
| `gini_coefficient` | Gini coefficient of merchant revenue distribution. For sorted revenues: `(2 * sum(i * rev_i)) / (n * total) - (n + 1) / n`. Single-merchant or zero-total countries return 0.0. |
| `median_merchant_revenue` | Median of per-merchant total revenue within country. |
| `premium_share` | Sum of revenue from `tier == "premium"` merchants / total country revenue. |

Sort: `[country]`. Round all floats to 6 decimal places.

---

## V2 Schema Changes

| V1 Column | V2 Column | Change |
|-----------|-----------|--------|
| `merchant_id` (int64) | `merchant_code` (str `"M00123"`) | Rename + type change |
| `event_date` (datetime UTC) | `event_ts` (str ISO `"2024-01-15T00:00:00+00:00"`) | Rename + type change |
| `revenue` (float64) | `revenue_cents` (int64) | Multiply by 100 |
| `cost` (float64) | `cost_cents` (int64) | Multiply by 100 |
| — | `currency` (str) | New column (per-country) |
| — | `channel` (str) | New column |
| `tier` | — | Dropped (now in merchants.parquet) |
| `event_month` | — | Dropped (derive from event_ts) |

## Reference Tables

- **`merchants.parquet`**: `merchant_code`, `merchant_id`, `tier`, `segment`,
  `onboarding_date`, `is_active` (bool, ~5% False)
- **`categories.parquet`**: `context_bucket`, `category_label`, `priority`, `sla_hours`

## Data Quarantine

Validate each v2 row. Invalid rows go to `quarantine.parquet` with an `error_code`.
Error code priority (first match wins):

1. **`NULL_REQUIRED`** — null or empty string in `merchant_code` or `country`
2. **`INVALID_DATE`** — `event_ts` is empty, unparseable, or year != 2024
3. **`NEGATIVE_AMOUNT`** — `revenue_cents < 0` or `cost_cents < 0`
4. **`MISSING_MERCHANT`** — `merchant_code` not found in merchants.parquet
5. **`INACTIVE_MERCHANT`** — merchant exists but `is_active == False`

## V2 Mode Outputs

V2 mode produces all v1-mode outputs (summary, top_merchants, quality,
merchant_analytics, country_summary) **plus** the following additional outputs.

### 1. `enriched_transactions.parquet`

Valid (non-quarantined) transactions after schema conversion, join, and enrichment.
Only rows with `has_answer == 1`.

Columns (in this order):

| Column | Source |
|--------|--------|
| `row_id` | Original |
| `merchant_id` | From merchants.parquet join on `merchant_code` |
| `country` | Original |
| `tier` | From merchants.parquet join |
| `segment` | From merchants.parquet join |
| `event_date` | Parsed from `event_ts` (UTC datetime) |
| `event_month` | Derived from `event_date`, formatted as `"YYYY-MM"` |
| `revenue` | `revenue_cents / 100.0` |
| `cost` | `cost_cents / 100.0` |
| `margin` | `revenue - cost` |
| `margin_pct` | `margin / revenue` (0.0 if `revenue == 0`) |
| `net_revenue` | `revenue - cost` |
| `profit_flag` | 1 if `net_revenue >= 25`, else 0 |
| `qa_score` | `(question_tokens * 1.3 + answer_tokens * 2.1) / (context_tokens + 10)` |
| `is_premium` | 1 if `tier == "premium"`, else 0 |
| `has_answer` | 1 if `answer_length > 0`, else 0 |
| `context_bucket` | `"short"` if `context_tokens < 120`, `"medium"` if `context_tokens < 360`, else `"long"` |
| `category_label` | From categories.parquet join on `context_bucket` |
| `priority` | From categories.parquet join on `context_bucket` |
| `sla_hours` | From categories.parquet join on `context_bucket` |
| `rolling_30d_revenue` | 30-day rolling sum of `revenue` per `merchant_id` (right-closed window including current row) |
| `revenue_rank` | Dense rank of `revenue` within `(country, tier)`, descending |
| `qa_percentile_band` | Percent rank of `qa_score` within `(country, tier)`, cut into `Q1`/`Q2`/`Q3`/`Q4` quartiles (Q1 = lowest 25%) |
| `z_score` | `(revenue - merchant_mean) / merchant_std` per `merchant_id` (ddof=1, fill NaN with 0.0) |
| `is_anomaly` | 1 if `abs(z_score) > 2`, else 0 |
| `monthly_cumulative_revenue` | Cumulative sum of `revenue` within `(merchant_id, event_month)` |
| `mom_revenue_growth` | Month-over-month revenue growth per merchant (null for first month) |

Sort: `[merchant_id, event_date, row_id]`. All floats rounded to 6 decimal places.

### 2. `quarantine.parquet`

All invalid rows in their **original v2 schema** (same columns as input_v2.parquet),
plus an `error_code` column (str).

Sort: `[row_id]`.

### 3. `quality_v2.json`

Compact JSON (no whitespace, sorted keys). Fields:

```json
{
  "distinct_merchants": <int>,
  "join_match_rate": <float, 6dp>,
  "mean_qa_score": <float, 6dp>,
  "pct_premium": <float, 6dp>,
  "quarantine_by_error": {"ERROR_CODE": <int>, ...},
  "quarantined_rows": <int>,
  "row_count": <int>,
  "run_id": "<YYYYMMDD-000000>",
  "schema_version": "v2",
  "top_country": "<str>",
  "total_input_rows": <int>,
  "valid_rows": <int>
}
```

## Lazy Execution Requirement

**Your pipeline MUST use `pl.scan_parquet()` and `pl.scan_csv()` instead of
`pl.read_parquet()` and `pl.read_csv()`.** Tests enforce this by monkey-patching
the eager read functions to raise RuntimeError. The pipeline must work with
lazy frames throughout, calling `.collect()` only when needed.

This applies to BOTH v1 and v2 code paths.

## Implementation Notes

- Implement inside the existing `/app/files/pipeline_polars.py` scaffold; preserve the helper structure and add logic inside it instead of replacing it wholesale.
- Keep the CLI contract unchanged.
- Keep deterministic schemas, sort order, and 6 decimal float rounding for every output.
- Use `scan_*` helpers and lazy Polars throughout both code paths; do not reintroduce eager `read_*`, pandas, or `to_pandas()`.

## Self-verification (important!)

Before completing, verify your solution against the visible tests:

    python3 -m pytest /app/files/tests.py -v

Do NOT use `python3 tests.py` -- test files require pytest. Running them directly with python silently does nothing.

## Scoring

- Core outputs (summary, top_merchants, quality) fail -> 0
- Core outputs pass, analytics (merchant_analytics, country_summary) fail -> 1/3
- Core + analytics pass, v2 outputs fail -> 2/3
- All pass -> 1.0

## Constraints

- Work offline in the container.
- Keep outputs deterministic.
- Do not modify test files.
