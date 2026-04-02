import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import numpy as np


def _array64(value, ndim: int | None = None) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    if ndim is not None:
        assert arr.ndim == ndim, f"expected {ndim}D output, got shape {arr.shape}"
    return arr


def _load_pipeline_module():
    pipeline_path = Path("/app/step_1/files/numpy_pipeline.py")
    spec = importlib.util.spec_from_file_location("numpy_pipeline", pipeline_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lib_rs_exists_and_implemented():
    p = Path("/app/src/lib.rs")
    assert p.exists(), "Missing /app/src/lib.rs"
    content = p.read_text()
    assert "todo!" not in content, "lib.rs still contains todo!() placeholders"
    assert len(content) > 800, "lib.rs is suspiciously short"


def test_package_builds():
    result = subprocess.run(
        ["maturin", "develop", "--release"],
        capture_output=True,
        text=True,
        cwd="/app",
        timeout=420,
    )
    assert result.returncode == 0, f"maturin build failed:\n{result.stderr[-3000:]}"


def test_cargo_dependencies_are_restricted():
    cargo_toml = Path("/app/Cargo.toml").read_text()
    match = re.search(r"(?ms)^\[dependencies\]\s*(.*?)(?:^\[|\Z)", cargo_toml)
    assert match is not None, "Cargo.toml must define a [dependencies] section"

    dependency_lines = [
        line.strip()
        for line in match.group(1).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    dependency_names = {
        line.split("=", 1)[0].strip() for line in dependency_lines if "=" in line
    }
    assert dependency_names == {"pyo3", "ndarray"}, (
        "Only `pyo3` and `ndarray` are allowed in Cargo.toml dependencies; "
        f"found {sorted(dependency_names)}"
    )


def test_rust_source_does_not_import_python_numpy():
    content = Path("/app/src/lib.rs").read_text()
    forbidden_patterns = (
        r'PyModule::import\s*\([^\)]*"numpy"',
        r'PyModule::import\s*\([^\)]*"scipy"',
        r'PyModule::import_bound\s*\([^\)]*"numpy"',
        r'PyModule::import_bound\s*\([^\)]*"scipy"',
        r"__import__",
        r"importlib",
    )
    for pattern in forbidden_patterns:
        assert re.search(pattern, content) is None, (
            "Rust source must not import or delegate to Python numpy/scipy via PyO3"
        )


def test_runtime_does_not_delegate_to_python_linalg(monkeypatch):
    import rustlinalg

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

    assert _array64(rustlinalg.matmul(a1, b1), 2).shape == (a1.shape[0], b1.shape[1])
    assert _array64(rustlinalg.cholesky(spd), 2).shape == spd.shape
    assert _array64(rustlinalg.solve_spd(spd, vec), 1).shape == vec.shape
    assert isinstance(rustlinalg.norm2(vec), float)
    q, r = rustlinalg.qr(a_qr)
    assert _array64(q, 2).shape == (a_qr.shape[0], a_qr.shape[0])
    assert _array64(r, 2).shape == a_qr.shape
    vals, vecs = rustlinalg.eig_symmetric(spd)
    assert _array64(vals, 1).shape == (spd.shape[0],)
    assert _array64(vecs, 2).shape == spd.shape
    u, sig, vt = rustlinalg.svd(a_svd)
    assert _array64(u, 2).shape == (a_svd.shape[0], a_svd.shape[0])
    assert _array64(sig, 1).shape == (min(a_svd.shape),)
    assert _array64(vt, 2).shape == (a_svd.shape[1], a_svd.shape[1])
    assert _array64(rustlinalg.matrix_exp(a_exp), 2).shape == a_exp.shape
    assert _array64(rustlinalg.solve_lstsq(a_ls, b_ls), 1).shape == (a_ls.shape[1],)


def test_import_all_functions():
    import rustlinalg

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
        assert hasattr(rustlinalg, name), f"Missing function: {name}"
        assert callable(getattr(rustlinalg, name)), f"{name} is not callable"


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
    import rustlinalg

    a1 = np.load("/app/fixtures/A_matmul.npy")
    b1 = np.load("/app/fixtures/B_matmul.npy")
    np.testing.assert_allclose(rustlinalg.matmul(a1, b1), a1 @ b1, rtol=1e-10)

    a2 = np.load("/app/fixtures/A_large.npy")[:24, :16]
    b2 = np.load("/app/fixtures/B_large.npy")[:16, :13]
    np.testing.assert_allclose(rustlinalg.matmul(a2, b2), a2 @ b2, rtol=1e-8)

    spd = np.load("/app/fixtures/A_spd.npy")
    vec = np.load("/app/fixtures/b_vec.npy")
    l = _array64(rustlinalg.cholesky(spd), 2)
    assert np.allclose(l, np.tril(l))
    np.testing.assert_allclose(l @ l.T, spd, rtol=1e-10)
    x = _array64(rustlinalg.solve_spd(spd, vec), 1)
    np.testing.assert_allclose(spd @ x, vec, rtol=1e-10)
    np.testing.assert_allclose(rustlinalg.norm2(x), np.linalg.norm(x), rtol=1e-12)


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
