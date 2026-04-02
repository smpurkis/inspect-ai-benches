# Rust/Python Linear Algebra Extension - Step 1

Build and install the extension and make it work with the provided numpy-driven pipeline script.

## Resources

- Build command: `maturin develop --release` from `/app`
- Pipeline script: `/app/step_1/files/numpy_pipeline.py`
- Primary implementation target: `/app/src/lib.rs` (PyO3 extension module `rustlinalg`)

## Dependency policy

- The Rust crate may depend only on `pyo3` and `ndarray`.
- Do not add the Rust `numpy` crate or any other Cargo dependency.
- Do not import Python `numpy` from Rust via PyO3.
- Python-facing return values may be plain nested Python lists / floats as long as they convert cleanly to `float64` NumPy arrays with the required shapes in the tests.

## Requirements

- Step 1 validates numerical parity vs trusted references over many inputs/code paths.

## Verification

- Tests at `/app/step_1/files/tests.py`

## Self-verification (important!)

Before completing this step, verify your solution against the visible tests:

    python3 -m pytest /app/step_1/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing.

## Scoring

- Step 1 fail → 0
- Step 1 pass, Step 2 fail → 1/3
- Step 1+2 pass, Step 3 fail → 2/3
- All pass → 1.0

## Constraints

- Work fully offline inside the container.
- Keep results deterministic.
- Do not modify test files under `/app/step_*/files/tests.py`.
- Do not modify verifier files.
