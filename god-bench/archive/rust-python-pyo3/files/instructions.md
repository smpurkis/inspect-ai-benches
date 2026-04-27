# Rust/PyO3 Linear Algebra Extension

Build a PyO3 extension module (`rustlinalg`) that implements ten linear algebra operations and passes the provided numpy-driven pipeline tests.

## Resources

- Stub file: `/app/src/lib.rs` (implement all ten functions)
- Cargo manifest: `/app/Cargo.toml`
- pyproject: `/app/pyproject.toml`
- Build command: `cd /app && maturin develop --release`
- Pipeline script: `/app/files/numpy_pipeline.py`
- Fixtures: `/app/fixtures/` -- `.npy` data files loaded by the tests

## Dependency policy

- All numerical computation must happen in Rust code in this crate.
- Allowed crate dependencies: `pyo3` and `ndarray` (basic features only — no linalg feature flags).
- Do **not** add `ndarray-linalg`, `nalgebra`, `nalgebra-lapack`, `lapack`, `lapack-sys`, `lapacke`, `lapacke-sys`, `blas`, `blas-src`, `cblas`, `cblas-sys`, `openblas-src`, `openblas-sys`, `intel-mkl-src`, `intel-mkl-sys`, `linfa-linalg`, `peroxide`, `argmin`, `russell`, `faer`, or any other linear algebra crate.
- Do **not** call back into Python `numpy.linalg` or `scipy.linalg` from Rust via PyO3.
- Do **not** use Cython, ctypes, or cffi in any part of the solution.
- numpy is permitted only on the Python boundary for accepting input arrays and returning output arrays. The actual computation must be in Rust.

## Required API

The compiled `rustlinalg` module must expose these functions:

| Function | Signature | Returns |
|---|---|---|
| `svd` | `svd(a)` | `(U, sigma, Vt)` -- full SVD |
| `schur` | `schur(a)` | `(T, Q)` -- real Schur decomposition |
| `matrix_log` | `matrix_log(a)` | matrix logarithm |
| `sqrtm` | `sqrtm(a)` | principal matrix square root |
| `qz` | `qz(a, b)` | `(S, T, Q, Z)` -- generalized Schur decomposition |
| `signm` | `signm(a)` | matrix sign function |
| `solve_sylvester` | `solve_sylvester(a, b, c)` | solution X of AX + XB = C |
| `eig` | `eig(a)` | `(real_parts, imag_parts, vectors)` -- nonsymmetric eigenvalues and eigenvectors |
| `ordschur` | `ordschur(t, q, select)` | `(T_new, Q_new)` -- reordered Schur decomposition |
| `matrix_power` | `matrix_power(a, p)` | A^p for real exponent p (fractional, negative allowed) |

Read the test file and pipeline script for exact expected arguments, return types, shapes, and edge-case behaviour. The tests compare your outputs against NumPy/SciPy reference results.

Functions should raise errors on invalid inputs (wrong shapes, non-square matrices where square is required, matrices with negative real eigenvalues where that is forbidden, etc.).

Inputs may arrive as numpy arrays. Returned values may be plain nested Python lists / floats / tuples as long as they convert cleanly to `float64` NumPy arrays with the required shapes in the tests.

## Constraints

- Only `pyo3` and `ndarray` (no extra features) are allowed as Cargo dependencies.
- Work fully offline inside the container (Cargo registry is mirrored into `/app/vendor/`).
- Keep results deterministic.
- Do not modify test or verifier files.

## Visible Tests

```
python3 -m pytest /app/files/tests.py -v
```
