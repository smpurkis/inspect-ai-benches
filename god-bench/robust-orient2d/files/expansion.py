"""Trusted zero-eliminating expansion arithmetic for binary64 values."""

from __future__ import annotations

SPLITTER = 134217729.0


def two_sum(a: float, b: float) -> tuple[float, float]:
    x = a + b
    bv = x - a
    av = x - bv
    return (a - av) + (b - bv), x


def two_diff(a: float, b: float) -> tuple[float, float]:
    x = a - b
    bv = a - x
    av = x + bv
    return (a - av) + (bv - b), x


def split(a: float) -> tuple[float, float]:
    c = SPLITTER * a
    high = c - (c - a)
    return high, a - high


def two_product(a: float, b: float) -> tuple[float, float]:
    x = a * b
    ahi, alo = split(a)
    bhi, blo = split(b)
    error = alo * blo - (((x - ahi * bhi) - alo * bhi) - ahi * blo)
    return error, x


def grow_expansion(expansion: list[float], value: float) -> list[float]:
    out: list[float] = []
    q = value
    for component in expansion:
        hh, q = two_sum(q, component)
        if hh:
            out.append(hh)
    if q or not out:
        out.append(q)
    return out


def expansion_sum(left: list[float], right: list[float]) -> list[float]:
    out = list(left)
    for component in right:
        out = grow_expansion(out, component)
    return out


def scale_expansion(expansion: list[float], scale: float) -> list[float]:
    out = [0.0]
    for component in expansion:
        low, high = two_product(component, scale)
        out = grow_expansion(out, low)
        out = grow_expansion(out, high)
    return out


def expansion_product(left: list[float], right: list[float]) -> list[float]:
    out = [0.0]
    for component in right:
        out = expansion_sum(out, scale_expansion(left, component))
    return out


def expansion_sign(expansion: list[float]) -> int:
    for component in reversed(expansion):
        if component > 0.0:
            return 1
        if component < 0.0:
            return -1
    return 0
