import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

FILES = Path("/app/files")
APP = Path("/app")


def _module():
    shutil.rmtree(APP / "src", ignore_errors=True)
    shutil.copytree(FILES / "src", APP / "src")
    shutil.copyfile(FILES / "Cargo.toml", APP / "Cargo.toml")
    shutil.copyfile(FILES / "pyproject.toml", APP / "pyproject.toml")
    result = subprocess.run(
        ["maturin", "develop", "--release", "--offline"], cwd=APP,
        capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    sys.modules.pop("rustlinalg", None)
    return importlib.import_module("rustlinalg.rustlinalg")


def _check(a, atol=2e-10):
    t, q = map(np.asarray, _module().schur(np.asarray(a, dtype=np.float64)))
    np.testing.assert_allclose(q.T @ q, np.eye(len(a)), atol=atol)
    np.testing.assert_allclose(q @ t @ q.T, a, atol=atol)
    assert np.max(np.abs(np.tril(t, -2)), initial=0.0) <= atol
    return t, q


def test_normal_case_real_and_complex_blocks():
    a = np.array([[3., 2., 1., 0.], [0., 1., -4., 2.], [0., 4., 1., 3.], [0., 0., 0., -2.]])
    t, _ = _check(a)
    assert np.any(np.abs(np.diag(t, -1)) > 1e-8)


def test_edge_case_singleton():
    t, q = _check(np.array([[7.25]]), atol=0.0)
    assert t[0, 0] == 7.25 and q[0, 0] == 1.0


def test_similarity_and_orthogonality_invariant():
    a = np.array([[1., 3., -2., 4.], [2., -1., 5., 0.5], [0., 2., 3., -4.], [1., 0., 2., 2.]])
    _check(a, atol=2e-9)


def test_deterministic_rerun():
    mod = _module()
    a = np.array([[2., -1., 0.], [0., 4., 3.], [0., 0., -5.]], dtype=np.float64)
    first = tuple(np.asarray(x) for x in mod.schur(a))
    second = tuple(np.asarray(x) for x in mod.schur(a))
    for x, y in zip(first, second):
        np.testing.assert_array_equal(x, y)
