# Rust/Python Linear Algebra Extension - Step 2

Precondition: complete this only after Step 1 passes.

Extend the Rust extension with three new operations: LU factorization with partial pivoting, a general linear system solver, and matrix determinant.

## New API

### `rustlinalg.lu_factor(a: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[int]]`

LU decomposition with partial pivoting. Given a square `float64` matrix `A`, return `(L, U, piv)` where:
- `L` is lower-triangular with unit diagonal, shape `(n, n)`
- `U` is upper-triangular, shape `(n, n)`
- `piv` is a list of `n` row pivot indices representing the permutation `P` such that `P @ A = L @ U`
- The pivot list `piv` encodes row swaps: `piv[i]` is the row that was swapped into position `i` during factorization

Return values may be plain nested Python lists / floats as long as they convert cleanly to `float64` NumPy arrays with the required shapes.

### `rustlinalg.solve(a: np.ndarray, b: np.ndarray) -> np.ndarray`

Solve `A x = b` for a general (not necessarily SPD) square non-singular `float64` matrix `A` and a `float64` vector `b`. Return `x` as a 1D array.

### `rustlinalg.det(a: np.ndarray) -> float`

Compute the determinant of a square `float64` matrix.

## Requirements

- All three functions must accept only `float64` square matrices (and for `solve`, a compatible-length `float64` vector).
- Invalid inputs (wrong shape, wrong dtype, non-square) must raise `ValueError`.
- Numerical results must match `np.linalg.solve` and `np.linalg.det` within reasonable tolerance (rtol=1e-8).
- For `lu_factor`: `L @ U` must reconstruct the permuted input within tolerance.

## Verification

- Tests at `/app/step_2/files/tests.py`

## Self-verification (important!)

Before completing this step, verify your solution against the visible tests:

    python3 -m pytest /app/step_2/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing.

## Scoring

- Step 1 fail → 0
- Step 1 pass, Step 2 fail → 1/3
- Step 1+2 pass, Step 3 fail → 2/3
- All pass → 1.0

## Constraints

- Work fully offline inside the container.
- Keep results deterministic.
- Keep the Step 1 dependency policy: only `pyo3` and `ndarray` are allowed in `Cargo.toml`, and Rust code must not import Python `numpy` via PyO3.
- Python-facing return values may be plain nested Python lists / floats as long as they convert cleanly to `float64` NumPy arrays with the required shapes in the tests.
- Do not modify test files under `/app/step_*/files/tests.py`.
- Do not modify verifier files.
