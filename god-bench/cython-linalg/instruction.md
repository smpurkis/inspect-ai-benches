# Real-Schur Block Reordering

Edit only `/app/files/reorder_kernel.pxi`. Implement `ordschur(T, Q, select) -> (T_new, Q_new)` for an existing real Schur decomposition `A = Q @ T @ Q.T`.

`T` and `Q` must be finite square `float64` arrays of equal shape, `Q` must be orthogonal, `T` must be upper quasi-triangular, and `select` must have length `n`. Reject invalid input with `ValueError`. Detect a 2x2 block from a significant `T[i+1, i]`, using a scale-aware tolerance no smaller than `64 * eps * max(1, max(abs(T)))`; selecting either member selects the whole block. Move selected blocks to the leading diagonal in their original relative order, keep unselected blocks in their original relative order, and never split a 2x2 block.

The trusted `cylinalg.pyx` supplies `_exchange_block`, a stable low-level real-Schur exchange primitive. It accepts mutable `T`, mutable `Q`, and zero-based source/destination scalar indices, updates both arrays, and returns LAPACK `info` (`0` means success). Your kernel must discover and track blocks and orchestrate these exchanges. Preserve reconstruction and orthogonality, return fresh C-contiguous arrays, and be deterministic. NumPy may only be used for array creation/marshalling; imports, Python or NumPy linear algebra, direct SciPy access, FFI, and added files are forbidden. A natural patch is 90-150 lines.

Build with `cd /app/files && python3 setup_build.py build_ext --inplace`.

Run `python3 -m pytest -q /app/files/tests.py`.
