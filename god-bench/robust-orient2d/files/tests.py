from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from predicates import classify_segments, orient2d


def test_normal_orientation_and_crossing() -> None:
    assert orient2d((0.0, 0.0), (4.0, 0.0), (1.0, 3.0)) == 1
    assert classify_segments((0.0, 0.0), (4.0, 4.0), (0.0, 4.0), (4.0, 0.0)) == "proper"


def test_edge_cases_for_collinear_and_point_segments() -> None:
    assert classify_segments((0.0, 0.0), (4.0, 0.0), (2.0, 0.0), (7.0, 0.0)) == "overlap"
    assert classify_segments((2.0, 0.0), (2.0, 0.0), (0.0, 0.0), (4.0, 0.0)) == "touch"
    assert classify_segments((5.0, 0.0), (5.0, 0.0), (0.0, 0.0), (4.0, 0.0)) == "disjoint"


def test_orientation_permutation_invariant() -> None:
    a, b, c = (1.25, -2.0), (9.0, 3.5), (-4.0, 8.0)
    sign = orient2d(a, b, c)
    assert sign != 0
    assert orient2d(b, a, c) == -sign
    assert orient2d(b, c, a) == sign


def test_runtime_is_deterministic() -> None:
    request = json.dumps({"op": "segments", "points": [[0, 0], [3, 3], [0, 3], [3, 0]]}) + "\n"
    command = [sys.executable, str(Path(__file__).with_name("predicate_runtime.py"))]
    first = subprocess.run(command, input=request, text=True, capture_output=True, check=True)
    second = subprocess.run(command, input=request, text=True, capture_output=True, check=True)
    assert first.stdout == second.stdout
    assert json.loads(first.stdout) == {"ok": True, "result": "proper"}


def test_non_finite_coordinates_are_rejected() -> None:
    with pytest.raises(ValueError):
        orient2d((0.0, 0.0), (1.0, 1.0), (float("inf"), 2.0))
