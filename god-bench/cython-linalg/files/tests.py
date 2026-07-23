import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


FILES = Path("/app/files")
PYX_SRC = FILES / "cylinalg.pyx"
API = (
    "svd", "schur", "matrix_log", "sqrtm", "qz", "signm",
    "solve_sylvester", "eig", "ordschur", "matrix_power",
)


def _build():
    return subprocess.run(
        [sys.executable, "setup_build.py", "build_ext", "--inplace"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(FILES),
    )


def _import_module():
    if not list(FILES.glob("cylinalg*.so")):
        result = _build()
        assert result.returncode == 0, result.stderr[-3000:]
    if "cylinalg" in sys.modules:
        del sys.modules["cylinalg"]
    return importlib.import_module("cylinalg")


def _load_pipeline():
    spec = importlib.util.spec_from_file_location(
        "numpy_pipeline", FILES / "numpy_pipeline.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cython_source_smoke():
    source = PYX_SRC.read_text()
    assert len(source) > 2000
    assert "STUB" not in source
    assert "cimport" in source or "cdef" in source


def test_module_builds():
    result = _build()
    assert result.returncode == 0, f"Cython build failed:\n{result.stderr[-3000:]}"
    assert list(FILES.glob("cylinalg*.so"))


def test_module_imports_with_complete_api():
    module = _import_module()
    for name in API:
        assert callable(getattr(module, name, None)), f"missing callable {name}"


def test_numpy_pipeline_smoke():
    cases = _load_pipeline().run_pipeline("cylinalg")
    assert len(cases) == 3
    for case in cases:
        errors = [value for key, value in case.items() if key != "case"]
        assert np.all(np.isfinite(errors))
        assert max(errors) < 1e-4


def test_svd_reconstruction_smoke():
    module = _import_module()
    matrix = np.load("/app/fixtures/A_svd_tall.npy")
    u, singular, vt = map(np.asarray, module.svd(matrix))
    k = min(matrix.shape)
    assert u.shape == (matrix.shape[0], matrix.shape[0])
    assert singular.shape == (k,)
    assert vt.shape == (matrix.shape[1], matrix.shape[1])
    assert np.all(singular >= 0.0) and np.all(np.diff(singular) <= 1e-10)
    np.testing.assert_allclose(
        u[:, :k] @ np.diag(singular) @ vt[:k], matrix, atol=1e-7
    )


def test_schur_reconstruction_smoke():
    module = _import_module()
    matrix = np.load("/app/fixtures/A_schur_general.npy")
    triangular, vectors = map(np.asarray, module.schur(matrix))
    np.testing.assert_allclose(vectors @ triangular @ vectors.T, matrix, atol=1e-7)
    np.testing.assert_allclose(vectors.T @ vectors, np.eye(matrix.shape[0]), atol=1e-9)


def test_invalid_shape_error_smoke():
    module = _import_module()
    with pytest.raises(Exception):
        module.schur(np.zeros((2, 3), dtype=np.float64))
    with pytest.raises(Exception):
        module.qz(np.eye(2), np.eye(3))


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
