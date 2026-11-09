# Francis Double-Shift QR Kernel

Edit only `src/francis.rs`. PyO3 marshaling, row-major matrix storage, Householder Hessenberg reduction, Schur iteration control, and Python wrappers are supplied and read-only.

Implement `francis_double_shift` as one implicit real double-shift sweep on the inclusive unreduced Hessenberg block `lo..=hi`. Form the shifts from its trailing 2x2 block, introduce and chase a three-entry bulge with stable Householder reflectors, apply every reflector from the left and right over the mathematically required ranges, and accumulate the right transformations into `q`. Preserve upper-Hessenberg structure and the similarity invariant.

Implement `deflatable` using a scale-aware, underflow-safe criterion. It must not split a coupled block merely because all entries are tiny, and it must work under multiplication of the matrix by very large or small powers of ten. Real 2x2 blocks are valid terminal Schur blocks.

Do not alter wrappers or add numerical dependencies. The expected solution changes roughly 110-150 lines. Python delegation and network access are forbidden.

Build with `cp /app/files/Cargo.toml /app/Cargo.toml && cp /app/files/pyproject.toml /app/pyproject.toml && rm -rf /app/src && cp -r /app/files/src /app/src && cd /app && maturin develop --release --offline`.

Run `python3 -m pytest -q /app/files/tests.py`.
