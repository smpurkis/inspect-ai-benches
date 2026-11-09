import importlib
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


FILES = Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def module():
    result = subprocess.run(
        [sys.executable, "setup_build.py", "build_ext", "--inplace"],
        cwd=FILES,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr[-4000:]
    sys.path.insert(0, str(FILES))
    sys.modules.pop("cylinalg", None)
    return importlib.import_module("cylinalg")


def test_normal_moves_selected_real_block(module):
    triangular = np.array([[3.0, 0.4, -0.2], [0.0, 1.0, 0.7], [0.0, 0.0, -2.0]])
    reordered, vectors = module.ordschur(triangular, np.eye(3), [False, False, True])
    assert reordered[0, 0] == pytest.approx(-2.0, abs=1e-12)
    np.testing.assert_allclose(vectors @ reordered @ vectors.T, triangular, atol=2e-13)


def test_edge_one_by_one(module):
    reordered, vectors = module.ordschur(np.array([[7.5]]), np.array([[-1.0]]), [True])
    np.testing.assert_array_equal(reordered, [[7.5]])
    np.testing.assert_array_equal(vectors, [[-1.0]])


def test_invariant_no_selection_preserves_decomposition(module):
    triangular = np.array([[2.0, 4.0, -1.0], [0.0, -3.0, 0.5], [0.0, 0.0, 8.0]])
    reordered, vectors = module.ordschur(triangular, np.eye(3), [False] * 3)
    np.testing.assert_allclose(vectors @ reordered @ vectors.T, triangular, atol=1e-14)
    np.testing.assert_allclose(vectors.T @ vectors, np.eye(3), atol=1e-14)
    assert reordered.flags.c_contiguous and vectors.flags.c_contiguous
    assert not np.shares_memory(reordered, triangular)


def test_deterministic_rerun(module):
    triangular = np.array([[4.0, 1.0, 2.0], [0.0, -1.0, 3.0], [0.0, 0.0, 0.5]])
    first = module.ordschur(triangular, np.eye(3), [False, True, False])
    second = module.ordschur(triangular, np.eye(3), [False, True, False])
    np.testing.assert_array_equal(first[0], second[0])
    np.testing.assert_array_equal(first[1], second[1])
