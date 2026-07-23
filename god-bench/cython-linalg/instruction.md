# Restricted Cython Linear Algebra

Edit only `cylinalg.pyx`. Implement the existing `cylinalg` API: `svd`, `schur`, `matrix_log`, `sqrtm`, `qz`, `signm`, `solve_sylvester`, `eig`, `ordschur`, and `matrix_power`.

Preserve signatures, return shapes, ordering, validation, and real-valued conventions documented in the source and exercised by `numpy_pipeline.py`. For `ordschur`, selecting either entry of a real-Schur conjugate 2x2 block selects and moves the whole block. Numerical computation must be implemented in Cython; NumPy is allowed only for array creation and marshalling. NumPy/SciPy linear algebra, BLAS/LAPACK, alternate FFI systems, network access, and nondeterministic behavior are forbidden.

Build with `cd /app/files && python3 setup_build.py build_ext --inplace`.

Run `python3 -m pytest -q /app/files/tests.py`.
