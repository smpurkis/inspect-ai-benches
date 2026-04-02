# Rust/Python Linear Algebra Extension - Step 3

Precondition: complete this only after Step 2 passes.

Extend the Rust extension with two advanced APIs:
- `rustlinalg.real_schur(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]`
- `rustlinalg.solve_care(a: np.ndarray, b: np.ndarray, q: np.ndarray, r: np.ndarray) -> np.ndarray`

You must implement both natively in Rust. Do not delegate to Python `numpy` or `scipy` from Rust via PyO3.

Python-facing return values may be plain nested Python lists / floats as long as they convert cleanly to `float64` NumPy arrays with the required shapes in the tests.

## `real_schur`

Accept only real square `float64` matrices.

Return `(Q, T)` values that convert cleanly to `float64` NumPy arrays, both with shape `(n, n)`, and satisfy all of the following:
- Orthogonality: `||Q^T Q - I||_F` is small
- Reconstruction: `||Q T Q^T - A||_F` is small
- `T` is real quasi-upper-triangular: entries below the first subdiagonal are negligible
- Any nonzero first-subdiagonal entry belongs to an isolated `2x2` block representing a complex-conjugate pair
- Expect harder real matrices too, including non-normal cases and cases whose Schur form contains multiple `2x2` complex-pair blocks
- Valid inputs may arrive as non-contiguous NumPy views / slices, not just contiguous arrays
- Invalid dimensions / invalid dtypes raise `ValueError`

## `solve_care`

Solve the continuous-time algebraic Riccati equation

`A^T X + X A - X B R^{-1} B^T X + Q = 0`

for the symmetric stabilizing solution `X`.

Accept only compatible real `float64` inputs with square `A`, symmetric square `Q`, and symmetric positive-definite square `R`.

Return `X` as a `float64` array with shape `(n, n)` and satisfy all of the following:
- `X` is symmetric within tolerance
- CARE residual is small
- The closed-loop matrix `A - B R^{-1} B^T X` is stable
- Expect more than one control/system family, including coupled systems and valid non-contiguous NumPy views / slices of the inputs
- Invalid dimensions / invalid dtypes / invalid matrix structure raise `ValueError`

## Signposts

- Read `/app/step_3/files/tests.py` carefully before finalizing; visible tests only cover part of the required contract.
- Hidden checks may exercise stronger but still in-scope cases from this written spec: non-contiguous views, non-normal Schur inputs, multiple `2x2` complex blocks, and stricter invalid-input handling.

## Requirements

- Any violation fails Step 3.

## Verification

- Tests at `/app/step_3/files/tests.py`

## Self-verification (important!)

Before completing this step, verify your solution against the visible tests:

    python3 -m pytest /app/step_3/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing.

## Scoring

- Step 1 fail -> 0
- Step 1 pass, Step 2 fail -> 1/3
- Step 1+2 pass, Step 3 fail -> 2/3
- All pass -> 1.0

## Constraints

- Work fully offline inside the container.
- Keep results deterministic.
- Keep the Step 1 dependency policy: only `pyo3` and `ndarray` are allowed in `Cargo.toml`, and Rust code must not import Python `numpy` via PyO3.
- Do not modify test files under `/app/step_*/files/tests.py`.
- Do not modify verifier files.
