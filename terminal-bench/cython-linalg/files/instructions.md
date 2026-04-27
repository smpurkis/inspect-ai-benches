# Cython Linear Algebra Extension

Build a Cython extension module (`cylinalg`) that implements ten linear algebra operations and passes the provided numpy-driven pipeline tests.

## Resources

- Stub file: `/app/files/cylinalg.pyx` (implement all ten functions)
- Build script: `/app/files/setup_build.py`
- Build command: `cd /app/files && python3 setup_build.py build_ext --inplace`
- Pipeline script: `/app/files/numpy_pipeline.py`
- Fixtures: `/app/fixtures/` -- `.npy` data files loaded by the tests

## Dependency policy

- All numerical computation must happen in Cython code. You may use `libc.math` (sqrt, exp, log, fabs, etc.), `libc.stdlib` (malloc, free), and `libc.string` (memset, memcpy).
- Do **not** call numpy.linalg, scipy.linalg, LAPACK, BLAS, or any external numerical library from within the module.
- Do **not** use ctypes, cffi, or PyO3.
- numpy is permitted only for array creation and data marshalling (accepting input arrays, returning output arrays). The actual computation must be in Cython.

## Required API

The compiled `cylinalg` module must expose these functions:

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

## Constraints

- Only `libc.math`, `libc.stdlib`, `libc.string`, and `numpy` (for array creation) are permitted.
- Work fully offline inside the container.
- Keep results deterministic.
- Do not modify test or verifier files.

## Visible Tests

```
python3 -m pytest /app/files/tests.py -v
```
