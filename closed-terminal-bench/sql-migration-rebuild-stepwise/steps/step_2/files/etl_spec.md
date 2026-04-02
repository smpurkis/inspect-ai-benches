# ETL Specification

## Overview

Load raw CSV data into the SQLite database created by the Step 1 migrations, then export a deterministic snapshot.

## Database Setup

1. Remove `/tmp/bench.db` if it exists
2. Run `migrate.py` from Step 1 to create the schema: `python3 /app/step_1/files/migrate.py /tmp/bench.db`
3. Enable foreign keys: `PRAGMA foreign_keys = ON`

## Data Loading Order

Load data in this exact order (foreign key dependencies):

### 1. Users (`raw_data/users.csv`)
- Insert each row into the `users` table
- Skip rows where `username` already exists (deduplicate by username)
- Skip rows where required fields (`username`, `email`) are empty
- Map CSV columns directly to table columns

### 2. Products (`raw_data/products.csv`)
- Insert each row into the `products` table
- Map CSV columns directly to table columns

### 3. Orders (`raw_data/orders.csv`)
- CSV contains: `id, user_id, product_id, quantity, ordered_at`
- The `total` column is NOT in the CSV — compute it as: `total = product.price * order.quantity`
- Look up the product price from the `products` table
- Insert into orders table with computed total

### 4. Reviews (`raw_data/reviews.csv`)
- CSV contains: `id, user_id, product_id, rating, comment, reviewed_at`
- **Skip** any review where the user has NOT placed an order for that product (check the `orders` table for a matching `user_id` + `product_id`)
- Empty `comment` field → insert as NULL
- Insert valid reviews into the `reviews` table

## Export

After loading all data, export to `/app/step_2/files/export.csv`:

```
--- users ---
<CSV header>
<rows ordered by id>

--- products ---
<CSV header>
<rows ordered by id>

--- orders ---
<CSV header>
<rows ordered by id>

--- reviews ---
<CSV header>
<rows ordered by id>

```

- Use `SELECT * FROM <table> ORDER BY id` for each table
- Write as standard CSV (comma-separated, no quoting unless needed)
- NULL values should be written as empty string
- End with a trailing newline after the last section
- Each section separated by a blank line

## CDC Processing (product_updates.csv)

`product_updates.csv` now contains an `applied_at` timestamp column. Records in the file are **not in chronological order**; you must sort them by `applied_at` ascending before applying.

Apply CDC operations in `applied_at` timestamp order (earliest first):
- `op=UPDATE`: Replace the product row with the updated values (by product_id). Update name, price, stock, and category from the CDC record. When two UPDATE records exist for the same product_id, the one with the **later** `applied_at` timestamp wins.
- `op=DELETE`: Remove the product row (by product_id); also remove all orders and reviews referencing this product_id.

Important: after applying all CDC operations in timestamp order, **load orders** using the post-CDC product prices. Orders referencing deleted products are skipped.

CDC must be idempotent: applying the same CDC file twice produces the same result.

## Determinism

- Process CSV rows in file order
- Export rows ordered by `id`
- Use consistent NULL handling (empty string in CSV)
