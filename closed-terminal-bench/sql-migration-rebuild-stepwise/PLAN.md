# SQL Migration Rebuild Stepwise Plan

This benchmark is a staged database engineering task focused on repairing a
broken migration chain, rebuilding a deterministic data transformation process,
and producing a fixed audit/report bundle from the resulting database.


## Benchmark Summary

Suggested task name:

- `sql-migration-rebuild-stepwise`

Core idea:

- Step 1 restores schema recreation from migrations.
- Step 2 reconstructs the data transformation pipeline from raw CSV inputs.
- Step 3 adds a deterministic reporting layer with strict output constraints.


## 3-Step Structure

### Step 1: Repair Migration Chain

Objective:

- Fix a broken SQL migration chain so a fresh database can be rebuilt from
  scratch.

What it tests:

- migration reasoning
- schema repair
- exact index/constraint/trigger recreation

Verification:

- migrations apply cleanly on a fresh DB
- resulting schema matches reference schema exactly
- required indexes, constraints, and triggers all exist


### Step 2: Rebuild Data Transformation Pipeline

Objective:

- Reconstruct the transformation pipeline that populates the schema from raw
  CSVs while preserving edge-case handling.

What it tests:

- ETL correctness
- null handling
- ordering determinism
- exact export fidelity

Verification:

- exported tables match reference outputs byte for byte
- row counts, null handling, and ordering are exact
- hidden inputs exercise edge cases not fully covered publicly


### Step 3: Add Deterministic Audit Bundle

Objective:

- Produce a fixed audit/report bundle from the migrated database.

What it tests:

- deterministic reporting SQL
- exact output ordering and formatting
- plan-constrained reporting behavior

Verification:

- report checksum matches expected output
- query plan stays within allowed constraints
- any deviation in content or ordering scores zero


## Implementation Notes

- choose one DB engine and keep it fixed, likely SQLite or Postgres
- schema comparison should normalize irrelevant metadata but keep structural
  requirements strict
- data exports should use canonical ordering and exact CSV rules
- query plan checks should focus on the one or two critical reports, not all SQL


## Final Recommendation

This is a strong benchmark if you want a database-focused staged task with a
clear progression from migrations to ETL to reporting.
