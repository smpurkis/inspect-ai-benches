import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import numpy as np


FILES = Path("/app/files")
LIB = FILES / "linalg.so"
C_SRC = FILES / "linalg.c"
PY_MODULE = FILES / "rustlinalg.py"


def _array64(value, ndim: int | None = None) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    if ndim is not None:
        assert arr.ndim == ndim, f"expected {ndim}D output, got shape {arr.shape}"
    return arr


def _import_module():
    spec = importlib.util.spec_from_file_location("rustlinalg", PY_MODULE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_pipeline_module():
    pipeline_path = Path("/app/files/numpy_pipeline.py")
    spec = importlib.util.spec_from_file_location("numpy_pipeline", pipeline_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_c_source_exists_and_implemented():
    assert C_SRC.exists(), "Missing /app/files/linalg.c"
    content = C_SRC.read_text()
    assert "todo" not in content.lower(), "linalg.c still contains TODO placeholders"
    assert len(content) > 800, "linalg.c is suspiciously short"


def test_shared_lib_builds():
    result = subprocess.run(
        ["gcc", "-O2", "-shared", "-fPIC", "-o", str(LIB), str(C_SRC), "-lm"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"gcc build failed:\n{result.stderr[-3000:]}"
    import ctypes
    lib = ctypes.CDLL(str(LIB))
    assert lib is not None, "ctypes.CDLL failed to load linalg.so"


def test_implementation_is_c_not_alternatives():
    assert PY_MODULE.exists(), f"{PY_MODULE} not found — must create ctypes wrapper"
    src = PY_MODULE.read_text()
    assert "ctypes" in src, "rustlinalg.py must use ctypes"
    assert "pyo3" not in src.lower(), "Must not use PyO3"
    assert "cffi" not in src.lower(), "Must not use cffi"
    assert "cython" not in src.lower(), "Must not use Cython"

    c_src = C_SRC.read_text()
    assert "double" in c_src, "linalg.c must use double-precision floating point"


def test_wrapper_does_not_import_linalg_libraries():
    content = PY_MODULE.read_text()
    forbidden_patterns = (
        r"numpy\.linalg",
        r"scipy\.linalg",
        r"from\s+numpy\s+import\s+linalg",
        r"from\s+scipy\s+import\s+linalg",
    )
    for pattern in forbidden_patterns:
        assert re.search(pattern, content) is None, (
            "rustlinalg.py must not import or delegate to numpy.linalg/scipy.linalg"
        )


def test_runtime_does_not_delegate_to_python_linalg(monkeypatch):
    mod = _import_module()

    def _blocked(*args, **kwargs):
        raise AssertionError(
            "rustlinalg must not delegate numerical work to Python numpy/scipy"
        )

    np_linalg_names = ["cholesky", "solve", "norm", "qr", "eigh", "svd", "eig", "lstsq"]
    for name in np_linalg_names:
        monkeypatch.setattr(np.linalg, name, _blocked)

    try:
        import scipy.linalg as scipy_linalg
    except Exception:
        scipy_linalg = None
    if scipy_linalg is not None:
        for name in ("cholesky", "solve", "qr", "eigh", "svd", "lstsq", "expm"):
            monkeypatch.setattr(scipy_linalg, name, _blocked, raising=False)

    a1 = np.load("/app/fixtures/A_matmul.npy")
    b1 = np.load("/app/fixtures/B_matmul.npy")
    spd = np.load("/app/fixtures/A_spd.npy")
    vec = np.load("/app/fixtures/b_vec.npy")
    a_qr = np.load("/app/fixtures/A_qr.npy")
    a_svd = np.load("/app/fixtures/A_svd_tall.npy")
    a_exp = np.load("/app/fixtures/A_exp_small.npy")
    a_ls = np.load("/app/fixtures/A_lstsq.npy")
    b_ls = np.load("/app/fixtures/b_lstsq.npy")

    assert _array64(mod.matmul(a1, b1), 2).shape == (a1.shape[0], b1.shape[1])
    assert _array64(mod.cholesky(spd), 2).shape == spd.shape
    assert _array64(mod.solve_spd(spd, vec), 1).shape == vec.shape
    assert isinstance(mod.norm2(vec), float)
    q, r = mod.qr(a_qr)
    assert _array64(q, 2).shape == (a_qr.shape[0], a_qr.shape[0])
    assert _array64(r, 2).shape == a_qr.shape
    vals, vecs = mod.eig_symmetric(spd)
    assert _array64(vals, 1).shape == (spd.shape[0],)
    assert _array64(vecs, 2).shape == spd.shape
    u, sig, vt = mod.svd(a_svd)
    assert _array64(u, 2).shape == (a_svd.shape[0], a_svd.shape[0])
    assert _array64(sig, 1).shape == (min(a_svd.shape),)
    assert _array64(vt, 2).shape == (a_svd.shape[1], a_svd.shape[1])
    assert _array64(mod.matrix_exp(a_exp), 2).shape == a_exp.shape
    assert _array64(mod.solve_lstsq(a_ls, b_ls), 1).shape == (a_ls.shape[1],)


def test_import_all_functions():
    mod = _import_module()

    for name in (
        "matmul",
        "cholesky",
        "solve_spd",
        "norm2",
        "qr",
        "eig_symmetric",
        "svd",
        "matrix_exp",
        "solve_lstsq",
    ):
        assert hasattr(mod, name), f"Missing function: {name}"
        assert callable(getattr(mod, name)), f"{name} is not callable"


def test_numpy_pipeline_matches_references():
    module = _load_pipeline_module()
    cases = module.run_pipeline("rustlinalg")
    assert len(cases) >= 3

    for item in cases:
        assert item["matmul_max_abs"] < 1e-8
        assert item["cholesky_recon_max_abs"] < 1e-8
        assert item["solve_spd_max_abs"] < 1e-8
        assert item["norm2_abs"] < 1e-9
        assert item["qr_recon_max_abs"] < 1e-7
        assert item["eig_vals_max_abs"] < 1e-7
        assert item["eig_recon_max_abs"] < 1e-6
        assert item["svd_vals_max_abs"] < 1e-6
        assert item["svd_recon_max_abs"] < 1e-6
        assert item["matrix_exp_max_abs"] < 5e-3
        assert item["lstsq_max_abs"] < 1e-7


def test_core_api_on_multiple_inputs():
    mod = _import_module()

    a1 = np.load("/app/fixtures/A_matmul.npy")
    b1 = np.load("/app/fixtures/B_matmul.npy")
    np.testing.assert_allclose(mod.matmul(a1, b1), a1 @ b1, rtol=1e-10)

    a2 = np.load("/app/fixtures/A_large.npy")[:24, :16]
    b2 = np.load("/app/fixtures/B_large.npy")[:16, :13]
    np.testing.assert_allclose(mod.matmul(a2, b2), a2 @ b2, rtol=1e-8)

    spd = np.load("/app/fixtures/A_spd.npy")
    vec = np.load("/app/fixtures/b_vec.npy")
    l = _array64(mod.cholesky(spd), 2)
    assert np.allclose(l, np.tril(l))
    np.testing.assert_allclose(l @ l.T, spd, rtol=1e-10)
    x = _array64(mod.solve_spd(spd, vec), 1)
    np.testing.assert_allclose(spd @ x, vec, rtol=1e-10)
    np.testing.assert_allclose(mod.norm2(x), np.linalg.norm(x), rtol=1e-12)


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
