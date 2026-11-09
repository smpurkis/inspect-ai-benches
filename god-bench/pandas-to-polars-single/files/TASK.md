# Lazy normalization kernel

Repair `normalize_and_quarantine(source, merchants)` in `normalization.py`. It must return two `pl.LazyFrame`s and must not collect or perform I/O.

Quarantine the first matching error: `NULL_REQUIRED` for null/blank `merchant_code` or `country`; `INVALID_DATE` for null/blank/unparseable `event_ts` or a parsed year other than 2024; `NEGATIVE_AMOUNT` for either cent amount below zero; `MISSING_MERCHANT` when the left join has no match; `INACTIVE_MERCHANT` when its match is inactive. Quarantine retains the original source columns, dtypes, values, and order, then `error_code`, sorted by `row_id`.

Valid output columns are exactly `NORMALIZED_COLUMNS`. Parse ISO-8601 offsets as instants in timezone-aware UTC, derive `event_month`, convert cents to `Float64` currency units, preserve optional text nulls, join merchant fields, and sort by `merchant_id,event_date,row_id`. Physical input order must not affect either result.

Only `normalization.py` is editable. Work offline, use lazy Polars only, and run `python3 -m pytest -q /app/files/tests.py`.
