# pandas-to-polars ETL specification

## Dataset source

Download the input Parquet from the Hugging Face Hub (offline fallback available):

- Dataset: `ibm/duorc`
- Config: `ParaphraseRC`
- Split: `train`
- Parquet URL:
  `https://huggingface.co/datasets/ibm/duorc/resolve/refs/convert/parquet/ParaphraseRC/train/0000.parquet`

The downloaded file is large enough to generate a 1,000,000 row dataset. Use a deterministic
random seed of `20260218` when sampling or shuffling. If offline, use
`/app/task-deps/source.parquet`.

## Input preparation (baseline does this)

1. Read the Parquet file into a pandas DataFrame.
2. Normalize the schema to the columns below (at least 20 columns total). Add derived columns
   as needed using deterministic logic.
3. Create a 1,000,000 row dataset by sampling with replacement from the source and applying
   deterministic transformations.
4. Persist the final dataset to `/data/input.parquet`.

### Required columns

The final dataset must contain the following columns, in this order:

1. `row_id` (int64)
2. `doc_id` (int64)
3. `question_id` (int64)
4. `qa_id` (int64)
5. `question` (string)
6. `context` (string)
7. `title` (string)
8. `answer` (string)
9. `answer_length` (int64)
10. `question_length` (int64)
11. `context_length` (int64)
12. `title_length` (int64)
13. `question_tokens` (int64)
14. `context_tokens` (int64)
15. `answer_tokens` (int64)
16. `title_tokens` (int64)
17. `has_answer` (int8)
18. `is_long_context` (int8)
19. `context_bucket` (string)
20. `question_bucket` (string)
21. `merchant_id` (int64)
22. `country` (string)
23. `event_date` (datetime, UTC)
24. `event_month` (string)
25. `revenue` (float64)
26. `cost` (float64)
27. `margin` (float64)
28. `margin_pct` (float64)
29. `is_premium` (int8)
30. `tier` (string)

## ETL pipeline (baseline pandas)

Inputs:

- `/data/input.parquet`

Outputs:

- `/app/out/summary.parquet`
- `/app/out/top_merchants.csv`
- `/app/out/quality.json`

### Pipeline steps

1. Load `/data/input.parquet` as a pandas DataFrame.
2. Filter out rows where `has_answer == 0`.
3. Create a `net_revenue` column: `revenue - cost`.
4. Create a `profit_flag` column: `1` if `net_revenue >= 25`, else `0`.
5. Create a `qa_score` column:
   - `qa_score = (question_tokens * 1.3 + answer_tokens * 2.1) / (context_tokens + 10)`.
6. Normalize buckets:
   - `context_bucket`:
     - `short` if `context_tokens < 120`
     - `medium` if `120 <= context_tokens < 360`
     - `long` if `context_tokens >= 360`
   - `question_bucket`:
     - `short` if `question_tokens < 12`
     - `medium` if `12 <= question_tokens < 22`
     - `long` if `question_tokens >= 22`
7. Build `/app/out/summary.parquet`:
   - Group by `country`, `tier`, `event_month`, `context_bucket`.
   - Aggregations:
     - `rows` = count
     - `avg_revenue` = mean of `revenue`
     - `avg_margin_pct` = mean of `margin_pct`
     - `p90_qa_score` = 90th percentile of `qa_score`
     - `profit_rate` = mean of `profit_flag`
   - Sort by `event_month` ascending, then `country`, `tier`, `context_bucket`.
8. Build `/app/out/top_merchants.csv`:
   - Group by `country` and `merchant_id`.
   - Aggregations:
     - `merchant_rows` = count
     - `merchant_revenue` = sum of `revenue`
     - `merchant_margin` = sum of `margin`
     - `merchant_avg_qa` = mean of `qa_score`
   - For each `country`, select the top 3 merchants by `merchant_revenue`.
   - Break ties by `merchant_margin` (desc), then `merchant_id` (asc).
   - Output columns: `country`, `merchant_id`, `merchant_revenue`, `merchant_margin`, `merchant_avg_qa`.
   - Sort by `country`, `merchant_revenue` descending, `merchant_id`.
9. Build `/app/out/quality.json`:
   - `row_count`: number of rows after filtering.
   - `distinct_merchants`: number of unique `merchant_id`.
   - `mean_qa_score`: mean of `qa_score`.
   - `pct_premium`: mean of `is_premium`.
   - `top_country`: country with highest row count (break ties alphabetically).
   - `run_id`: formatted as `YYYYMMDD-000000` using the max `event_date`.

## Notes

- For `/app/out/summary.parquet` and `/app/out/top_merchants.csv`, round all float outputs to 6 decimal places.
- For `/app/out/quality.json`, round float values to 6 decimal places.
- The pandas pipeline is intentionally slow. The rewrite must match outputs exactly.
- The Polars pipeline should not call `to_pandas()` or rely on pandas intermediates.
