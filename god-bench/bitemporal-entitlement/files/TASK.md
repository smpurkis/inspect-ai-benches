# Bitemporal Entitlement Query

Edit exactly `/app/files/query.sql`.

Complete the PostgreSQL query that resolves one entitlement for the single row in `query_context`. Select history for the same tenant, subject, and entitlement key whose half-open valid interval contains `business_time` and whose half-open system interval contains `audit_time`. A `NULL` interval end means infinity.

If rows overlap, the winner is the greatest `system_from`, then greatest `valid_from`, then greatest `revision_id`. Return no row when there is no winner or the winner is a tombstone. Otherwise return exactly `tenant_id, subject_id, entitlement_key, value, valid_from, valid_to, system_from, system_to, revision_id` in that order. Timestamp comparisons use PostgreSQL `timestamptz` semantics.

Only `query.sql` is editable. Do not change the schema, runner, tests, or PostgreSQL configuration. No extensions, procedural SQL, writes, DDL, session changes, external programs, or network access are allowed. The submitted file must be one read-only `SELECT` or `WITH ... SELECT` statement and must not depend on row insertion order.

Run `python3 -m pytest -q /app/files/tests.py`.
