"""Candidate circle-box manifold and accumulated impulse kernels."""

from __future__ import annotations

import math
from typing import Any

Body = dict[str, Any]
Manifold = tuple[tuple[float, float], float, tuple[float, float]]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def clamp_normal(accumulated: float, raw: float) -> tuple[float, float]:
    """Return the new non-negative accumulator and the impulse delta."""
    # BUG: raw is an increment, not a replacement, and delta is relative to old.
    new = max(0.0, raw)
    return new, new


def clamp_friction(
    accumulated: float, raw: float, mu: float, normal_accumulated: float
) -> tuple[float, float]:
    """Return the Coulomb-clamped accumulator and its impulse delta."""
    limit = mu * normal_accumulated
    # BUG: clamp accumulated + raw and apply only new - accumulated.
    new = max(-limit, min(limit, raw))
    return new, new


def circle_box_manifold(circle: Body, box: Body) -> Manifold | None:
    """Return (box-to-circle normal, penetration, circle contact), or None.

    BUGGY STARTER: this treats every box as axis-aligned and cannot select a
    stable face when the circle center is inside the box.
    """
    dx, dy = circle["x"] - box["x"], circle["y"] - box["y"]
    hw, hh = box["w"] / 2.0, box["h"] / 2.0
    closest = (max(-hw, min(hw, dx)), max(-hh, min(hh, dy)))
    offset = (dx - closest[0], dy - closest[1])
    distance = math.hypot(*offset)
    if distance >= circle["r"]:
        return None
    normal = (1.0, 0.0) if distance == 0.0 else (offset[0] / distance, offset[1] / distance)
    point = (circle["x"] - circle["r"] * normal[0],
             circle["y"] - circle["r"] * normal[1])
    return normal, circle["r"] - distance, point


def _apply(body: Body, impulse, lever, sign, inertia: float) -> None:
    body["vx"] += sign * impulse[0] / body["mass"]
    body["vy"] += sign * impulse[1] / body["mass"]
    body["omega"] += sign * _cross(lever, impulse) / inertia


def solve_contact(
    a: Body,
    b: Body,
    normal: tuple[float, float],
    point: tuple[float, float],
    accumulated: tuple[float, float],
    inertia_a: float,
    inertia_b: float,
) -> tuple[float, float]:
    """Apply one sequential normal/friction iteration and return accumulators.

    BUGGY STARTER: it applies raw impulses every iteration and clamps friction
    against that raw normal impulse instead of accumulated normal support.
    """
    ra, rb = (point[0] - a["x"], point[1] - a["y"]), (point[0] - b["x"], point[1] - b["y"])
    va = (a["vx"] - a["omega"] * ra[1], a["vy"] + a["omega"] * ra[0])
    vb = (b["vx"] - b["omega"] * rb[1], b["vy"] + b["omega"] * rb[0])
    relative = (va[0] - vb[0], va[1] - vb[1])
    vn = _dot(relative, normal)
    if vn >= 0.0:
        return accumulated
    restitution = 0.0 if abs(vn) < 1.0 else math.sqrt(a["e"] * b["e"])
    denom = (1 / a["mass"] + 1 / b["mass"] + _cross(ra, normal) ** 2 / inertia_a
             + _cross(rb, normal) ** 2 / inertia_b)
    raw_n = -(1.0 + restitution) * vn / denom
    new_n, delta_n = clamp_normal(accumulated[0], raw_n)
    impulse = (delta_n * normal[0], delta_n * normal[1])
    _apply(a, impulse, ra, 1.0, inertia_a)
    _apply(b, impulse, rb, -1.0, inertia_b)

    va = (a["vx"] - a["omega"] * ra[1], a["vy"] + a["omega"] * ra[0])
    vb = (b["vx"] - b["omega"] * rb[1], b["vy"] + b["omega"] * rb[0])
    relative = (va[0] - vb[0], va[1] - vb[1])
    tangent_v = (relative[0] - _dot(relative, normal) * normal[0],
                 relative[1] - _dot(relative, normal) * normal[1])
    length = math.hypot(*tangent_v)
    if length <= 1e-10:
        return new_n, accumulated[1]
    tangent = (tangent_v[0] / length, tangent_v[1] / length)
    denom = (1 / a["mass"] + 1 / b["mass"] + _cross(ra, tangent) ** 2 / inertia_a
             + _cross(rb, tangent) ** 2 / inertia_b)
    raw_t = -length / denom
    new_t, delta_t = clamp_friction(
        accumulated[1], raw_t, math.sqrt(a["mu"] * b["mu"]), new_n
    )
    impulse = (delta_t * tangent[0], delta_t * tangent[1])
    _apply(a, impulse, ra, 1.0, inertia_a)
    _apply(b, impulse, rb, -1.0, inertia_b)
    return new_n, new_t
