# Audit Report — Step 3

Generate a deterministic formatted audit report from the populated database.

## Context

The database at `/tmp/bench.db` is now populated with data (from Step 2, including CDC changes). Write `/app/step_3/files/audit_report.py` that queries the database and produces a formatted text report.

## Requirements

Write `audit_report.py` that:
1. Connects to `/tmp/bench.db`
2. Queries aggregate statistics and computes cohort retention and rolling averages
3. Writes a formatted report to `/app/step_3/files/report.txt`
4. The report must be generated strictly according to `report_spec.md`

There is no public reference file — you must implement the logic described in `report_spec.md` correctly. Determinism is critical: two runs on the same database must produce byte-identical output.

See `report_spec.md` for the full report format specification, including:
- Summary section (totals)
- Top 5 products by revenue (ties broken alphabetically)
- Cohort retention table (monthly user retention)
- 30-day rolling revenue average (per day with orders)

## Verification

    python3 -m pytest /app/step_3/files/tests.py -v

## Files

- `report_spec.md` — Detailed report format specification
- You must create: `audit_report.py`

## Constraints

- Work entirely offline inside the container
- Report must be fully deterministic
- Do not modify test files
- Use the database at `/tmp/bench.db` (populated by Step 2)
- Use the fixed timestamp `2024-03-01 00:00:00` — do NOT use the current system time
