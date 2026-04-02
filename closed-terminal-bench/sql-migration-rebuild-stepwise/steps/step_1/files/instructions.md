# SQL Migration Repair — Step 1

Fix the broken SQL migration files in `/app/step_1/files/migrations/` so they apply cleanly and produce the correct database schema.

## Context

You have 7 SQL migration files that create a small e-commerce database (users, products, orders, reviews, categories, and a price-change audit trail). Each migration contains intentional errors — wrong types, missing constraints, syntax issues, and logic bugs in triggers. The migration runner (`migrate.py`) is correct and should NOT be modified.

## Requirements

- Fix all 7 migration files so `migrate.py` runs without errors on a fresh SQLite database
- The resulting schema must satisfy all tests (run `tests.py` to verify)
- `reference_schema.sql` describes the target schema in plain English — use it as a guide
- Correct column types and constraints (NOT NULL, UNIQUE, CHECK, DEFAULT)
- Correct foreign key references with proper ON DELETE rules
- All required indexes with correct names
- Both triggers must have correct syntax AND correct logic
- Do NOT modify `migrate.py`, `reference_schema.sql`, or any test file

## Files

- `migrations/001_create_users.sql` — BROKEN: fix type and constraint issues
- `migrations/002_create_products.sql` — BROKEN: fix CHECK constraint and DEFAULT
- `migrations/003_create_orders.sql` — BROKEN: fix foreign key reference and CASCADE
- `migrations/004_create_reviews.sql` — BROKEN: fix CHECK range and add UNIQUE constraint
- `migrations/005_add_indexes_triggers.sql` — BROKEN: fix index names and trigger syntax
- `migrations/006_create_categories.sql` — BROKEN: partial index references a non-existent column
- `migrations/007_add_price_tracking.sql` — BROKEN: trigger has logic errors (see file)
- `migrate.py` — Migration runner (correct, do not modify)
- `reference_schema.sql` — Schema description (plain English, no SQL DDL)

## Verification

Run the visible tests:

    python3 -m pytest /app/step_1/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest.

## Scoring

- Step 1 fail → 0
- Step 1 pass, Step 2 fail → 1/3
- Step 1+2 pass, Step 3 fail → 2/3
- All pass → 1.0

## Constraints

- Work entirely offline inside the container
- Keep outputs deterministic
- Do not modify test files, `migrate.py`, or `reference_schema.sql`
