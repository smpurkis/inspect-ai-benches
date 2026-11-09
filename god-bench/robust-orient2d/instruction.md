# Robust 2D Predicates

Edit only `predicates.py`. Repair `orient2d(a, b, c)` and `classify_segments(a, b, c, d)` without changing their signatures or return values.

`orient2d` accepts three finite binary64 points whose coordinates are zero or have magnitude in `[1e-100, 1e140]`, and returns exactly `-1`, `0`, or `1`, matching the sign of the determinant over the exact values represented by those floats. Use the supplied `expansion.py` arithmetic for the uncertain fallback; `Fraction`, `Decimal`, symbolic packages, bit-level rational reconstruction, and new dependencies are forbidden.

`classify_segments` returns `"proper"`, `"touch"`, `"overlap"`, or `"disjoint"`. It must handle reversed endpoints, zero-length segments, exact endpoint contact, collinear overlap, and nearly collinear coordinates. `proper` means one interior crossing, `touch` means exactly one shared point (including a point segment on another segment), and `overlap` means a collinear intersection containing more than one point.

The protected expansion primitives and JSON-lines runtime harness are supplied. Work offline, keep results deterministic, and do not modify any file except `predicates.py`.

Run `python3 -m pytest -q /app/files/tests.py`.
