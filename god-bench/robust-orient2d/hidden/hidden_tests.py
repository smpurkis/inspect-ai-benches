from __future__ import annotations

import ast
from fractions import Fraction
import json
import math
from pathlib import Path
import random
import subprocess
import sys

import pytest

FILES = Path("/app/files")
if not FILES.exists():
    FILES = Path(__file__).resolve().parents[1] / "files"
sys.path.insert(0, str(FILES))

import predicates


def exact_sign(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> int:
    ax, ay = map(Fraction.from_float, a)
    bx, by = map(Fraction.from_float, b)
    cx, cy = map(Fraction.from_float, c)
    determinant = (ax - cx) * (by - cy) - (ay - cy) * (bx - cx)
    return (determinant > 0) - (determinant < 0)


def on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> bool:
    return exact_sign(a, b, p) == 0 and all(
        min(a[index], b[index]) <= p[index] <= max(a[index], b[index]) for index in (0, 1)
    )


def segment_oracle(a, b, c, d) -> str:
    signs = exact_sign(a, b, c), exact_sign(a, b, d), exact_sign(c, d, a), exact_sign(c, d, b)
    if signs[0] * signs[1] < 0 and signs[2] * signs[3] < 0:
        return "proper"
    hits = []
    for point in (a, b):
        if on_segment(c, d, point) and point not in hits:
            hits.append(point)
    for point in (c, d):
        if on_segment(a, b, point) and point not in hits:
            hits.append(point)
    if not hits:
        return "disjoint"
    if len(hits) == 1:
        return "touch"
    return "overlap"


def hard_triples() -> list[tuple[tuple[float, float], ...]]:
    # Products lose the unit determinant in ordinary binary64 subtraction.
    triples = []
    for base, flip in ((2**52, 1), (-2**52, -1), (0, 1)):
        a = (float(base), float(base))
        b = (float(base + 100000001), float(base + 100000000))
        c = (float(base + 200000003), float(base + 200000001))
        triples.append((a, b, c) if flip > 0 else (a, c, b))
    return triples


def test_exact_rational_oracle_on_generated_binary64_points() -> None:
    rng = random.Random(0x0A17E2D)
    cases = list(hard_triples())
    for _ in range(320):
        exponent = rng.randrange(-80, 90)
        points = tuple(
            (math.ldexp(rng.randrange(-(1 << 30), 1 << 30), exponent),
             math.ldexp(rng.randrange(-(1 << 30), 1 << 30), exponent))
            for _ in range(3)
        )
        cases.append(points)
    for a, b, c in cases:
        assert predicates.orient2d(a, b, c) == exact_sign(a, b, c)


def test_translation_scaling_and_permutation_metamorphisms() -> None:
    transforms = ((0.0, 0.0, 1.0), (1024.0, -4096.0, 1.0), (0.0, 0.0, 2.0**37), (0.0, 0.0, 2.0**-41))
    for triple in hard_triples() + [((1.5, -8.0), (7.25, 3.0), (-4.0, 9.5))]:
        for tx, ty, scale in transforms:
            a, b, c = tuple(((x + tx) * scale, (y + ty) * scale) for x, y in triple)
            expected = exact_sign(a, b, c)
            assert predicates.orient2d(a, b, c) == expected
            assert predicates.orient2d(b, a, c) == -expected
            assert predicates.orient2d(b, c, a) == expected


def test_generated_segment_classes_and_endpoint_permutations() -> None:
    rng = random.Random(20260726)
    cases = [
        ((0.0, 0.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0)),
        ((2.0, 2.0), (2.0, 2.0), (0.0, 0.0), (4.0, 4.0)),
        ((0.0, 0.0), (8.0, 8.0), (3.0, 3.0), (12.0, 12.0)),
        ((0.0, 0.0), (3.0, 3.0), (4.0, 4.0), (9.0, 9.0)),
    ]
    for _ in range(180):
        cases.append(tuple((float(rng.randrange(-100, 101)), float(rng.randrange(-100, 101))) for _ in range(4)))
    for case in cases:
        expected = segment_oracle(*case)
        variants = (case, (case[1], case[0], case[2], case[3]), (case[0], case[1], case[3], case[2]), (case[2], case[3], case[0], case[1]))
        assert all(predicates.classify_segments(*variant) == expected for variant in variants)


def test_uncertain_path_reaches_protected_expansion_primitives(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    original = predicates.expansion_product

    def observed(left, right):
        nonlocal calls
        calls += 1
        return original(left, right)

    monkeypatch.setattr(predicates, "expansion_product", observed)
    a, b, c = hard_triples()[0]
    assert predicates.orient2d(a, b, c) == exact_sign(a, b, c)
    assert calls >= 2, "uncertain determinant bypassed the supplied exact arithmetic"


def test_single_input_mutations_change_orientation_and_classification() -> None:
    a, b, _ = hard_triples()[0]
    c = b
    mutated = (c[0], math.nextafter(c[1], math.inf))
    assert exact_sign(a, b, c) != exact_sign(a, b, mutated)
    assert predicates.orient2d(a, b, c) == exact_sign(a, b, c)
    assert predicates.orient2d(a, b, mutated) == exact_sign(a, b, mutated)
    segment = (a, b, c, c)
    changed = (a, b, mutated, mutated)
    assert segment_oracle(*segment) != segment_oracle(*changed)
    assert predicates.classify_segments(*segment) == segment_oracle(*segment)
    assert predicates.classify_segments(*changed) == segment_oracle(*changed)


def test_kernel_has_no_exact_oracle_or_runtime_bypass() -> None:
    source = (FILES / "predicates.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
    forbidden = {"fractions", "Fraction", "decimal", "Decimal", "struct", "ctypes", "subprocess"}
    assert not imported.intersection(forbidden)
    assert "as_integer_ratio" not in source and "predicate_runtime" not in source


def test_protected_json_runtime_executes_candidate_kernel() -> None:
    a, b, c = hard_triples()[0]
    requests = [
        {"op": "orient", "points": [a, b, c]},
        {"op": "segments", "points": [a, b, c, c]},
    ]
    payload = "".join(json.dumps(item) + "\n" for item in requests)
    run = subprocess.run([sys.executable, str(FILES / "predicate_runtime.py")], input=payload, text=True, capture_output=True, check=True)
    replies = [json.loads(line) for line in run.stdout.splitlines()]
    assert replies == [
        {"ok": True, "result": exact_sign(a, b, c)},
        {"ok": True, "result": segment_oracle(a, b, c, c)},
    ]
