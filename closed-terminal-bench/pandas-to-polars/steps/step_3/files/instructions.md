# pandas->polars Step 3: Schema Evolution + Lazy Execution + Data Quarantine

Further extend `/app/step_1/files/pipeline_polars.py` to handle a schema-evolved
input format (v2), join with reference tables, quarantine bad rows, and use
**lazy execution** throughout.

## Resources

- Pandas reference: `/app/step_3/files/pipeline_pandas_v2.py` (read-only)
- V2 public input: `/app/step_3/files/public_data/input_v2.parquet`
- Reference tables: `/app/step_3/files/public_data/merchants.parquet`,
  `/app/step_3/files/public_data/categories.parquet`
- Schema mapping: `/app/step_3/files/public_data/schema_mapping.json`
- Expected outputs: `/app/step_3/files/public_data/expected/`

## CLI contract (unchanged)

```
python3 /app/step_1/files/pipeline_polars.py --in <input_dir> --out <output_dir>
```

## Schema Detection

- If `input_v2.parquet` exists in `--in` dir → **v2 mode**
- Otherwise `input.parquet` → **v1 mode** (produces step 1+2 outputs only)

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

## V2 Mode Outputs (in addition to step 1+2 outputs)

### 1. `enriched_transactions.parquet`

Valid (non-quarantined) transactions after schema conversion, join, and enrichment.
Only rows with `has_answer == 1`.

Columns (in this order):

| Column | Source |
|--------|--------|
| `row_id` | Original |
| `merchant_id` | From merchants.parquet join |
| `country` | Original |
| `tier` | From merchants.parquet join |
| `segment` | From merchants.parquet join |
| `event_date` | Parsed from event_ts |
| `event_month` | Derived from event_date |
| `revenue` | revenue_cents / 100.0 |
| `cost` | cost_cents / 100.0 |
| `margin` | revenue - cost |
| `margin_pct` | margin / revenue (0 if revenue == 0) |
| `net_revenue` | revenue - cost |
| `profit_flag` | 1 if net_revenue >= 25, else 0 |
| `qa_score` | Same formula as step 1 |
| `is_premium` | 1 if tier == "premium" |
| `has_answer` | 1 if answer_length > 0 |
| `context_bucket` | Same as step 1 |
| `category_label` | From categories.parquet join on context_bucket |
| `priority` | From categories.parquet join |
| `sla_hours` | From categories.parquet join |
| `rolling_30d_revenue` | Same as step 2 |
| `revenue_rank` | Same as step 2 |
| `qa_percentile_band` | Same as step 2 |
| `z_score` | Same as step 2 |
| `is_anomaly` | Same as step 2 |
| `monthly_cumulative_revenue` | Same as step 2 |
| `mom_revenue_growth` | Same as step 2 |

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

## Regression checklist

- Continue extending the same `/app/step_1/files/pipeline_polars.py` scaffold; preserve the helper structure and add logic inside it instead of replacing it wholesale.
- Keep the CLI contract unchanged and preserve the Step 1 and Step 2 outputs for v1 input.
- Keep deterministic schemas, sort order, and 6 decimal float rounding for every output that existed before this step.
- Use `scan_*` helpers and lazy Polars throughout both code paths; do not reintroduce eager `read_*`, pandas, or `to_pandas()`.

## Self-verification (important!)

Before completing this step, verify your solution against the visible tests:

    python3 -m pytest /app/step_3/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing.

## Scoring

- Step 1 fail -> 0
- Step 1 pass, Step 2 fail -> 1/3
- Step 1+2 pass, Step 3 fail -> 2/3
- All pass -> 1.0

## Constraints

- Work offline in the container.
- Keep outputs deterministic.
- Do not modify test files.
