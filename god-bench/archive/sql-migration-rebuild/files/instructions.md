# SQL Migration Repair

Fix the broken SQL migration files in `/app/files/migrations/` so they apply cleanly and produce the correct database schema.

## Context

You have 7 SQL migration files that create a small e-commerce database (users, products, orders, reviews, categories, and a price-change audit trail). The migrations contain errors — some cause runtime failures, others produce a schema that silently deviates from the requirements. The migration runner (`migrate.py`) is correct and should NOT be modified.

**Important:** Comments in the SQL files may be outdated or incorrect. Always trust the requirements document over inline comments.

## Requirements

- Fix all migration files so `migrate.py` runs without errors on a fresh SQLite database
- The resulting schema must match the requirements described in `requirements.md`
- Do NOT modify `migrate.py`, `requirements.md`, or any test file

## Files

- `migrations/` — 7 SQL migration files (these need fixing)
- `migrate.py` — Migration runner (correct, do not modify)
- `requirements.md` — Authoritative schema requirements

## Verification

    python3 -m pytest /app/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest.

## Constraints

- Work entirely offline inside the container
- Keep outputs deterministic
- Do not modify test files, `migrate.py`, or `requirements.md`
