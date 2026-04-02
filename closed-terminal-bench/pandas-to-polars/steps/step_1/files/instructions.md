# pandas->polars Step 1 (semantic parity)

Migrate the pandas pipeline to Polars with semantically equivalent outputs.

## Resources

- Baseline pandas: `/app/step_1/files/pipeline_pandas.py`
- Candidate file to edit: `/app/step_1/files/pipeline_polars.py`
- Full ETL spec: `/app/step_1/files/spec.md`
- Public input: `/app/step_1/files/public_data/input.parquet`

## CLI contract

```
python3 /app/step_1/files/pipeline_polars.py --in <input_dir> --out <output_dir>
```

## Required outputs in `<output_dir>`

- `summary.parquet`
- `top_merchants.csv`
- `quality.json`

## Core transformation contract

You should not need to mine `spec.md` for the scoring-critical logic. Implement these rules directly:

1. Load `input.parquet` from `--in`.
2. Filter to rows where `has_answer == 1`.
3. Add derived columns:
   - `net_revenue = revenue - cost`
   - `profit_flag = 1` if `net_revenue >= 25`, else `0`
   - `qa_score = (question_tokens * 1.3 + answer_tokens * 2.1) / (context_tokens + 10)`
4. Normalize buckets from token counts, even if bucket-like columns already exist:
   - `context_bucket`: `short` if `context_tokens < 120`, `medium` if `120 <= context_tokens < 360`, else `long`
   - `question_bucket`: `short` if `question_tokens < 12`, `medium` if `12 <= question_tokens < 22`, else `long`

## Output contracts

### `summary.parquet`

- Group by `country`, `tier`, `event_month`, `context_bucket`.
- Output columns: `country`, `tier`, `event_month`, `context_bucket`, `rows`, `avg_revenue`, `avg_margin_pct`, `p90_qa_score`, `profit_rate`.
- Aggregations:
  - `rows` = count
  - `avg_revenue` = mean of `revenue`
  - `avg_margin_pct` = mean of `margin_pct`
  - `p90_qa_score` = 90th percentile of `qa_score`
  - `profit_rate` = mean of `profit_flag`
- Sort by `event_month` ascending, then `country`, `tier`, `context_bucket`.

### `top_merchants.csv`

- Group by `country`, `merchant_id`.
- Aggregations:
  - `merchant_rows` = count
  - `merchant_revenue` = sum of `revenue`
  - `merchant_margin` = sum of `margin`
  - `merchant_avg_qa` = mean of `qa_score`
- Within each `country`, keep the top 3 merchants by `merchant_revenue`.
- Break ties by `merchant_margin` descending, then `merchant_id` ascending.
- Output columns: `country`, `merchant_id`, `merchant_revenue`, `merchant_margin`, `merchant_avg_qa`.
- Final sort: `country`, `merchant_revenue` descending, `merchant_id`.

### `quality.json`

- Include exactly these fields: `row_count`, `distinct_merchants`, `mean_qa_score`, `pct_premium`, `top_country`, `run_id`.
- `row_count`: rows after the `has_answer == 1` filter.
- `distinct_merchants`: distinct `merchant_id` count.
- `mean_qa_score`: mean of `qa_score`.
- `pct_premium`: mean of `is_premium`.
- `top_country`: country with the highest row count after filtering; break ties alphabetically.
- `run_id`: `YYYYMMDD-000000` using the max `event_date`.

## Determinism and numeric expectations

- Match the pandas baseline semantically: same rows, columns, values, and JSON fields, with normal float tolerance.
- Round all float outputs in `summary.parquet`, `top_merchants.csv`, and `quality.json` to 6 decimal places.
- Keep filenames, schemas, sort order, and JSON formatting deterministic.

## Constraints

- Use Polars; do not use pandas intermediates and do not call `to_pandas()`.
- Work offline in the container.
- Keep outputs deterministic.
- Do not modify test files under `/app/step_*/files/tests.py`.
- Do not modify verifier files.

## Self-verification (important!)

Before completing this step, verify your solution against the visible tests:

    python3 -m pytest /app/step_1/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing.

## Scoring

- Step 1 fail -> 0
- Step 1 pass, Step 2 fail -> 1/3
- Step 1+2 pass, Step 3 fail -> 2/3
- All pass -> 1.0
