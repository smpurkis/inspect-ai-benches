import importlib
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


FILES = Path("/app/files")
APP = Path("/app")
LIB_RS = FILES / "src" / "lib.rs"
API = (
    "svd", "schur", "matrix_log", "sqrtm", "qz", "signm",
    "solve_sylvester", "eig", "ordschur", "matrix_power",
)


def _stage_source():
    live = APP / "src" / "lib.rs"
    changed = not live.exists() or live.read_bytes() != LIB_RS.read_bytes()
    shutil.copyfile(LIB_RS, live)
    return changed


def _patch_maturin_init():
    import site

    for site_packages in site.getsitepackages():
        init_path = Path(site_packages) / "rustlinalg" / "__init__.py"
        if init_path.exists():
            init_path.write_text("from .rustlinalg import *\n")


def _build():
    _stage_source()
    result = subprocess.run(
        ["maturin", "develop", "--release"],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(APP),
    )
    if result.returncode == 0:
        _patch_maturin_init()
    return result


def _import_module():
    changed = _stage_source()
    if changed:
        result = _build()
        assert result.returncode == 0, result.stderr[-3000:]
    try:
        if "rustlinalg" in sys.modules:
            del sys.modules["rustlinalg"]
        return importlib.import_module("rustlinalg")
    except ImportError:
        result = _build()
        assert result.returncode == 0, result.stderr[-3000:]
        return importlib.import_module("rustlinalg")


def _load_pipeline():
    spec = importlib.util.spec_from_file_location(
        "numpy_pipeline", FILES / "numpy_pipeline.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rust_source_smoke():
    source = LIB_RS.read_text()
    assert len(source) > 2000
    assert not re.search(r"\b(?:todo|unimplemented)!\s*\(", source)
    assert "pyo3" in source.lower() and "pymodule" in source


def test_module_builds():
    result = _build()
    assert result.returncode == 0, f"maturin develop failed:\n{result.stderr[-3000:]}"


def test_module_imports_with_complete_api():
    module = _import_module()
    for name in API:
        assert callable(getattr(module, name, None)), f"missing callable {name}"


def test_numpy_pipeline_smoke():
    cases = _load_pipeline().run_pipeline("rustlinalg")
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


def test_invalid_input_error_smoke():
    module = _import_module()
    with pytest.raises(Exception):
        module.schur(np.zeros((2, 3), dtype=np.float64))
    with pytest.raises(Exception):
        module.svd(np.eye(3, dtype=np.float32))


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
