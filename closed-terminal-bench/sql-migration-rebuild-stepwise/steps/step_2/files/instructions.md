# ETL Pipeline — Step 2

Build an ETL script that loads raw CSV data into the migrated database and exports a deterministic reference CSV.

## Context

The database schema is now correct (from Step 1). You need to write `/app/step_2/files/etl.py` that:
1. Creates a fresh database with the schema from Step 1
2. Loads CSV data from `raw_data/`
3. Exports the populated tables to `export.csv`

## Requirements

Write `etl.py` that performs the following (see `etl_spec.md` for details):

1. Run the migrations from Step 1 on a fresh database at `/tmp/bench.db`
2. Load `raw_data/users.csv` into the `users` table (skip duplicates by username)
3. Load `raw_data/products.csv` into the `products` table
4. Apply CDC operations from `raw_data/product_updates.csv` **sorted by `applied_at` ascending** (timestamp order, not file order): UPDATE rows replace existing product data (later timestamp wins for the same product), DELETE rows remove the product and all its associated orders and reviews
5. Load `raw_data/orders.csv` into the `orders` table, computing `total = price * quantity` by joining with the products table (skip orders for deleted products)
6. Load `raw_data/reviews.csv` into the `reviews` table, skipping reviews where the user has not ordered that product (also skip reviews for deleted products)
7. Handle empty fields: empty `comment` → NULL. Skip rows with empty required fields (e.g., empty email).
8. Export all tables to `/app/step_2/files/export.csv` in the format matching `reference_export_public.csv`

The CDC processing must be idempotent: running the ETL script twice produces the same result.

## Export Format

The export file has sections for each table:
```
--- users ---
id,username,email,created_at,is_active
1,alice,alice@example.com,2024-01-15 10:00:00,1
...

--- products ---
...
```

Each section: header line `--- <table> ---`, then CSV header row, then data rows ordered by `id`.

## Verification

    python3 -m pytest /app/step_2/files/tests.py -v

## Files

- `raw_data/users.csv`, `products.csv`, `orders.csv`, `reviews.csv` — Input data
- `raw_data/product_updates.csv` — CDC operations to apply after initial product load
- `etl_spec.md` — Detailed ETL specification
- `reference_export_public.csv` — Expected export output (reflects CDC changes)
- You must create: `etl.py`

## Constraints

- Work entirely offline inside the container
- Keep outputs deterministic
- Do not modify test files or reference files
