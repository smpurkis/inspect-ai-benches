# pandas->polars Step 2: Window Functions + Complex Aggregation

Extend `/app/step_1/files/pipeline_polars.py` to produce **two new output files**
alongside the original Step 1 outputs.

## Resources

- Pandas reference: `/app/step_2/files/pipeline_pandas_advanced.py` (read-only)
- Public input (same as Step 1): `/app/step_1/files/public_data/input.parquet`
- Expected outputs: `/app/step_2/files/public_data/expected/`

## CLI contract (unchanged)

```
python3 /app/step_1/files/pipeline_polars.py --in <input_dir> --out <output_dir>
```

## New required outputs in `<output_dir>`

### 1. `merchant_analytics.parquet`

Per-transaction enrichment. Same rows as `has_answer == 1` filtered data.

Columns (in this order):

| Column | Description |
|--------|-------------|
| `row_id` | Row identifier (int64) |
| `merchant_id` | Merchant identifier (int64) |
| `country` | Country code (str) |
| `tier` | "premium" or "standard" (str) |
| `event_date` | Event timestamp (datetime UTC) |
| `event_month` | "YYYY-MM" (str) |
| `revenue` | Revenue amount (float64) |
| `cost` | Cost amount (float64) |
| `qa_score` | QA score (float64) |
| `rolling_30d_revenue` | Rolling 30-day revenue sum per merchant. Window: right-closed `(t-30D, t]`. Data must be sorted by event_date within each merchant group. (float64) |
| `revenue_rank` | Dense rank of revenue within (country, tier), descending. Rank 1 = highest. (int64) |
| `qa_percentile_band` | Quartile of qa_score within (country, tier). Use percent rank (average method), then bin: Q1=[0, 0.25], Q2=(0.25, 0.5], Q3=(0.5, 0.75], Q4=(0.75, 1.0]. (str) |
| `z_score` | Z-score of revenue within merchant. Use sample std (ddof=1). **Merchants with 1 transaction have undefined std — set z_score to 0.0.** (float64) |
| `is_anomaly` | 1 if abs(z_score) > 2, else 0 (int8) |
| `monthly_cumulative_revenue` | Cumulative sum of revenue within (merchant_id, event_month), ordered by event_date then row_id. (float64) |
| `mom_revenue_growth` | Month-over-month revenue growth per merchant. `(current_month_total - prev_month_total) / prev_month_total`. Null/NaN for the first month. (float64) |

Sort: `[merchant_id, event_date, row_id]`. All floats rounded to 6 decimal places.

### 2. `country_summary.parquet`

Per-country concentration metrics. One row per country.

| Column | Description |
|--------|-------------|
| `country` | Country code (str) |
| `hhi` | Herfindahl-Hirschman Index. Sum of squared merchant revenue shares within country. (float64) |
| `top3_share` | Fraction of country revenue from top 3 merchants (by total revenue). (float64) |
| `merchant_count` | Number of distinct merchants in country. (int64) |
| `gini_coefficient` | Gini coefficient of merchant revenue distribution. Formula: `(2 * sum(i * r_i)) / (n * sum(r_i)) - (n+1)/n` where r_i are sorted ascending. Return 0 for single-merchant countries. (float64) |
| `median_merchant_revenue` | Median of total merchant revenue per country. (float64) |
| `premium_share` | Fraction of country revenue from premium-tier merchants. 0 if no premium merchants. (float64) |

Sort: `[country]`. All floats rounded to 6 decimal places.

## Step 1 outputs must still be produced

Your pipeline must continue to produce `summary.parquet`, `top_merchants.csv`,
and `quality.json` exactly as in Step 1.

## Regression checklist

- Keep extending `/app/step_1/files/pipeline_polars.py`; preserve its helper structure instead of replacing the CLI, version detection, or writer helpers.
- Do not regress the existing Step 1 contracts: same output filenames, schemas, sort order, deterministic formatting, and 6 decimal float rounding.
- Add the Step 2 outputs alongside the Step 1 outputs; do not stop writing earlier artifacts.
- Keep the scaffold readable with small composable helpers so later steps can build on it.

## Self-verification (important!)

Before completing this step, verify your solution against the visible tests:

    python3 -m pytest /app/step_2/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing.

## Scoring

- Step 1 fail -> 0
- Step 1 pass, Step 2 fail -> 1/3
- Step 1+2 pass, Step 3 fail -> 2/3
- All pass -> 1.0

## Constraints

- Work offline in the container.
- Keep outputs deterministic.
- Do not modify test files under `/app/step_*/files/tests.py`.
