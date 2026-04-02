# Compression Algorithm Step 3 (>=40% improvement)

Precondition: complete this only after Step 2 passes.

Improve the Step 2 WASM compression method so output is at least 40% smaller than Step 2 while preserving exact roundtrip. The visible tests require only 15% improvement, but held-out tests require 40% — aim for the higher bar.

## Requirements

- Step 3 compressed output size must be <= 60% of Step 2 compressed size on held-out datasets.
- Step 3 compressed output size must also be <= 60% of the original input size on held-out datasets.
- The visible tests use a 85% threshold; do not treat that as the real target.
- This Step 3 improvement requirement applies to the WASM/WASI implementation only.

## Verification

- Tests at `/app/step_3/files/tests.py`

## Self-verification (important!)

Before completing this step, verify your solution against the visible tests:

    python3 -m pytest /app/step_3/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing.

## Scoring

- Step 1 fail → 0
- Step 1 pass, Step 2 fail → 1/3
- Step 1+2 pass, Step 3 fail → 2/3
- All pass → 1.0

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify verifier files.
- You may add helper source/build scripts under `/app/step_3/files`.
