# PyO3 Linear Algebra Kernel

Edit only `src/lib.rs`. Implement the existing `rustlinalg` API: `svd`, `schur`, `matrix_log`, `sqrtm`, `qz`, `signm`, `solve_sylvester`, `eig`, `ordschur`, and `matrix_power`.

Preserve signatures, return shapes, ordering, validation, and real-valued conventions documented in the source and exercised by `numpy_pipeline.py`. For `ordschur`, selecting either entry of a real-Schur conjugate 2x2 block selects and moves the whole block. All matrix storage and numerical computation must be implemented in this Rust crate using only PyO3 and the standard library. PyO3 may marshal inputs and outputs but must not import, evaluate, or call Python numerical code. Python numerical delegation, linear-algebra crates, alternate FFI systems, network access, and nondeterministic behavior are forbidden.

Build with `cp /app/files/src/lib.rs /app/src/lib.rs && cd /app && maturin develop --release`.

Run `python3 -m pytest -q /app/files/tests.py`.
