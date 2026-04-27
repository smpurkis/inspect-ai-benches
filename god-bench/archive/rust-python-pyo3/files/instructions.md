# Rust/Python Linear Algebra Extension (PyO3)

Build a PyO3 extension module (`rustlinalg`) that implements linear algebra operations and passes the provided numpy-driven pipeline tests.

## Resources

- Build command: `maturin develop --release` from `/app`
- Pipeline script: `/app/files/numpy_pipeline.py`
- Primary implementation target: `/app/src/lib.rs` (PyO3 extension module `rustlinalg`)

## Dependency policy

- The Rust crate may depend only on `pyo3` and `ndarray`.
- Do not add the Rust `numpy` crate or any other Cargo dependency.
- Do not import Python `numpy` from Rust via PyO3.
- Python-facing return values may be plain nested Python lists / floats as long as they convert cleanly to `float64` NumPy arrays with the required shapes in the tests.

## Required API

The `rustlinalg` module must expose these functions:

```python
import rustlinalg

rustlinalg.matmul(a, b)           # matrix multiply → 2D array
rustlinalg.cholesky(a)            # Cholesky decomposition (lower triangular L where A = L·Lᵀ)
rustlinalg.solve_spd(a, b)       # solve Ax = b for symmetric positive-definite A
rustlinalg.norm2(v)               # L2 norm of a vector → float
rustlinalg.qr(a)                  # QR decomposition → (Q, R) tuple
rustlinalg.eig_symmetric(a)      # eigendecomposition of symmetric matrix → (vals, vecs)
rustlinalg.svd(a)                 # singular value decomposition → (U, S, Vt)
rustlinalg.matrix_exp(a)         # matrix exponential
rustlinalg.solve_lstsq(a, b)    # least-squares solution to Ax ≈ b
```

## Verification

    python3 -m pytest /app/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing.

## Constraints

- Work fully offline inside the container.
- Keep results deterministic.
- Do not modify test or verifier files.
