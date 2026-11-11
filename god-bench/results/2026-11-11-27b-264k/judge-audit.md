# GOD-Bench judge audit — 27B vs NF Stream

Date: 2026-11-10
Scope: hidden-test verifier (`common/harbor_verifier.py`) and the two tasks where
the 27B appears to beat NF Stream: `bitemporal-entitlement` and `robust-orient2d`.

## Bottom line

The verifier is not generally broken: no verifier exceptions, no false passes,
and no usage/budget failures were found. However, two hidden tests produce
**false negatives** that directly affect the 27B-vs-NF comparison:

1. `bitemporal-entitlement`: NF's query is rejected because a semicolon appears
   in a SQL **comment**. The query is a single read-only `WITH ... SELECT` and
   passes the other 15 hidden tests.
2. `robust-orient2d`: NF's exact fallback is rejected because it does not import
   the specific symbol `expansion_product`, even though it uses the supplied
   `scale_expansion`, `two_sum`, `two_diff`, and `expansion_sign` primitives and
   passes the other 6 hidden tests.

Both are implementation-prescriptive / textual checks, not behavioral failures.
The 27B passes both because it happened to avoid a comment semicolon and to
import the exact helper name.

## Evidence

### 1. `bitemporal-entitlement` — semicolon in a comment

NF result: 0/5 attempts; every attempt has public 4/4, hidden 15/16, and fails
only:

```
FAILED hidden/hidden_tests.py::test_query_is_read_only_single_statement_and_reaches_kernel
```

Hidden test:

```python
source = open("/app/files/query.sql", encoding="utf-8").read()
...
assert ";" not in source.strip().rstrip(";"), "submit exactly one SQL statement"
```

NF query (all five attempts have the same line):

```sql
-- greatest revision_id; a tombstone winner yields no row.
```

The query is a single read-only `WITH ... SELECT`; the semicolon is inside a
comment, not a statement terminator. The test fails at the raw-text assertion
before it reaches the kernel check. The 27B query has only the final trailing
semicolon, so it passes 16/16.

This is a clear verifier bug. Fix: strip line comments (`-- ...`) and block
comments (`/* ... */`) before the single-statement check, or use a SQL parser
to count statements. Add a regression test with a semicolon inside a comment.

### 2. `robust-orient2d` — exact symbol required by monkeypatch

NF result: 0/5 attempts; every attempt has public 1.0, hidden 6/7, and fails only:

```
FAILED hidden/hidden_tests.py::test_uncertain_path_reaches_protected_expansion_primitives
```

The test does:

```python
original = predicates.expansion_product
...
monkeypatch.setattr(predicates, "expansion_product", observed)
a, b, c = hard_triples()[0]
assert predicates.orient2d(a, b, c) == exact_sign(a, b, c)
assert calls >= 2
```

NF's `predicates.py` imports:

```python
from expansion import expansion_sign, scale_expansion, two_diff, two_sum
```

and builds an exact product from `scale_expansion` + `two_sum`. It does not
import `expansion_product`, so the test raises:

```
AttributeError: module 'predicates' has no attribute 'expansion_product'
```

before it checks the determinant or call count. NF passes the other six hidden
tests, including hard triples, single-input mutations, no-oracle/no-forbidden
imports, and the protected JSON runtime. The contract only requires "uncertain
determinants must use the supplied expansion.py primitives" (plural); it does
not require `expansion_product` by name.

This one is more debatable than the semicolon bug, but the test is checking an
undocumented implementation detail and fails at attribute access rather than at
behavior. The 27B imports `expansion_product` and calls it twice, so it passes
7/7.

Fix: monkeypatch `expansion.expansion_product` (or count calls to any supplied
exact primitive such as `scale_expansion` / `two_sum`), or inspect the AST for
imports/calls to supplied primitives. Do not require a specific symbol. Add a
regression case for a candidate that uses `scale_expansion`/`two_sum` directly.

## Impact on the comparison

NF raw: **31/100 attempts, 7/20 tasks**.
NF with the two false negatives corrected: **41/100 attempts, 9/20 tasks**.

27B current: **24/64 attempts (37.5%), 8/20 tasks** (still running;
64/100 completed, 2 running, 34 pending, 0 errors/retries, ETA roughly 4.8 h
from 2026-11-10T21:38Z).

The 27B's task set is:

```
aligned-reallocator, async-cache-generation, bitemporal-entitlement,
capability-module-loader, pandas-to-polars-single, physics-2d,
robust-orient2d, wasm-compression-wat
```

NF's corrected task set is the same eight **plus** `msgpack-incremental`
(NF 4/5, 27B 0/3). So the 27B is not genuinely ahead on task coverage:
its apparent 8-vs-7 lead comes from the two judge false negatives. At attempt
level, NF's corrected 41% is also above the 27B's current 37.5%.

The 27B's only genuine relative advantage is the pass rate on
`wasm-compression-wat` (2/3 vs NF 2/5), but both solve the task. NF's clear
genuine win is `msgpack-incremental`.

## What is not a judge problem

- No verifier errors, exceptions, or missing usage artifacts in the completed
  trials.
- No false passes found: 27B's other passing tasks pass complete hidden suites,
  and the verifier resets `/app/files` to pristine, overlays only editable files,
  and runs public + hidden tests.
- NF's other failures (e.g. `cython-linalg`, `rust-python-pyo3`,
  `cifar10-burn`, `samscript-*`) are real functional hidden-test failures, not
  structural false negatives.
- The 27B's `msgpack-incremental` failures are real test failures/timeouts, not
  verifier errors.
- Minor reporting quirk: some trials are labeled `failure_category: timeout`
  even when the public/hidden log shows an ordinary test failure (e.g. 27B
  `msgpack`). This does not change the correctness score, but the category is
  misleading.

## Recommended next steps

1. Do not change the official run mid-flight. Finish the 27B run first.
2. Patch the two hidden tests as above and add regression cases.
3. Rescore the saved candidate artifacts for `bitemporal-entitlement` and
   `robust-orient2d` without rerunning the models; the artifact files are
   preserved under each trial's `artifacts/app/files/`.
4. Recompute the final table with both raw and judge-corrected scores. The
   corrected comparison should show NF at least level with, and on task
   coverage ahead of, the 27B.
