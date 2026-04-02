# C/Python Linear Algebra Extension (ctypes)

Build a C shared library and Python ctypes wrapper module (`rustlinalg`) that implements linear algebra operations and passes the provided numpy-driven pipeline tests.

## Resources

- Build command: `gcc -O2 -shared -fPIC -o /app/files/linalg.so /app/files/linalg.c -lm`
- Pipeline script: `/app/files/numpy_pipeline.py`
- C implementation: `/app/files/linalg.c` (you create this)
- Python wrapper: `/app/files/rustlinalg.py` (you create this — must use ctypes to load `linalg.so`)

## Dependency policy

- The C code may only use standard C libraries (`<math.h>`, `<stdlib.h>`, `<string.h>`, etc.).
- Do not link against LAPACK, BLAS, OpenBLAS, or any external numerical library.
- The Python wrapper must use `ctypes` only — no PyO3, no cffi, no Cython.
- Do not delegate numerical work to numpy/scipy from the wrapper; the C library must perform all computation.

## Required API

The `rustlinalg` module (your `/app/files/rustlinalg.py`) must expose these functions:

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

All inputs are float64 numpy arrays. All outputs should convert cleanly to float64 numpy arrays with the required shapes.

## Verification

    python3 -m pytest /app/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing.

## Constraints

- Work fully offline inside the container.
- Keep results deterministic.
- Do not modify test or verifier files.
