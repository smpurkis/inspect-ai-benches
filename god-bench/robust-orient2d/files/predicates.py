"""Candidate kernel: robust orientation and closed-segment classification."""

from __future__ import annotations

import math

from expansion import expansion_product, expansion_sign, expansion_sum, scale_expansion, two_diff

Point = tuple[float, float]


def _point(point: Point) -> Point:
    valid = lambda value: math.isfinite(value) and (value == 0.0 or 1e-100 <= abs(value) <= 1e140)
    if len(point) != 2 or not all(valid(value) for value in point):
        raise ValueError("coordinates must be zero or have magnitude in [1e-100, 1e140]")
    return point


def orient2d(a: Point, b: Point, c: Point) -> int:
    """Return the exact orientation sign of the represented binary64 points."""
    a, b, c = _point(a), _point(b), _point(c)
    acx, acy = a[0] - c[0], a[1] - c[1]
    bcx, bcy = b[0] - c[0], b[1] - c[1]
    left, right = acx * bcy, acy * bcx
    determinant = left - right
    bound = 3.3306690738754716e-16 * (abs(left) + abs(right))
    if abs(determinant) > bound:
        return 1 if determinant > 0.0 else -1

    # BUG: cancellation in this uncertain region is currently treated as collinear.
    return 0


def classify_segments(a: Point, b: Point, c: Point, d: Point) -> str:
    """Classify the intersection of two closed segments."""
    a, b, c, d = _point(a), _point(b), _point(c), _point(d)
    signs = (
        orient2d(a, b, c),
        orient2d(a, b, d),
        orient2d(c, d, a),
        orient2d(c, d, b),
    )
    if signs[0] * signs[1] < 0 and signs[2] * signs[3] < 0:
        return "proper"
    if a == c or a == d or b == c or b == d:
        return "touch"
    # BUG: interior touches and collinear intervals are not implemented.
    return "disjoint"
