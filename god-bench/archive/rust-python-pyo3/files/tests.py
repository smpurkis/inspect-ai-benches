import importlib
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


FILES = Path("/app/files")
APP = Path("/app")
LIB_RS = APP / "src" / "lib.rs"
CARGO_TOML = APP / "Cargo.toml"


def _patch_maturin_init():
    """Patch maturin's auto-generated __init__.py which has a broken self-reference."""
    import site
    for sp in site.getsitepackages():
        init_path = Path(sp) / "rustlinalg" / "__init__.py"
        if init_path.exists():
            init_path.write_text("from .rustlinalg import *\n")


def _build_if_needed():
    """Run `maturin develop --release` if rustlinalg is not yet importable."""
    try:
        if "rustlinalg" in sys.modules:
            del sys.modules["rustlinalg"]
        importlib.import_module("rustlinalg")
        return
    except Exception:
        pass

    result = subprocess.run(
        ["maturin", "develop", "--release"],
        capture_output=True, text=True, timeout=600, cwd=str(APP),
    )
    if result.returncode != 0:
        pytest.fail(f"maturin develop failed:\n{result.stderr[-3000:]}")

    _patch_maturin_init()


def _import_module():
    _build_if_needed()
    if "rustlinalg" in sys.modules:
        del sys.modules["rustlinalg"]
    return importlib.import_module("rustlinalg")


def _load_pipeline_module():
    pipeline_path = FILES / "numpy_pipeline.py"
    spec = importlib.util.spec_from_file_location("numpy_pipeline", pipeline_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _array64(value, ndim=None):
    arr = np.asarray(value, dtype=np.float64)
    if ndim is not None:
        assert arr.ndim == ndim, f"expected {ndim}D output, got shape {arr.shape}"
    return arr


# ===================================================================
# Structural tests
# ===================================================================


def test_rust_source_exists_and_implemented():
    assert LIB_RS.exists(), "Missing /app/src/lib.rs"
    content = LIB_RS.read_text()
    assert len(content) > 2000, "src/lib.rs is suspiciously short"
    todo_count = len(re.findall(r"\btodo!\s*\(", content)) + len(re.findall(r"\bunimplemented!\s*\(", content))
    assert todo_count == 0, f"src/lib.rs still has {todo_count} todo!/unimplemented! placeholder(s)"


def test_module_builds_successfully():
    result = subprocess.run(
        ["maturin", "develop", "--release"],
        capture_output=True, text=True, timeout=600, cwd=str(APP),
    )
    assert result.returncode == 0, f"maturin develop failed:\n{result.stderr[-3000:]}"
    _patch_maturin_init()
    if "rustlinalg" in sys.modules:
        del sys.modules["rustlinalg"]
    importlib.import_module("rustlinalg")


def test_implementation_is_pyo3_not_alternatives():
    assert LIB_RS.exists(), "src/lib.rs not found"
    src = LIB_RS.read_text()
    assert "pyo3" in src.lower(), "src/lib.rs must use PyO3"
    assert "#[pymodule]" in src or "pymodule" in src, "src/lib.rs must define a PyO3 module"
    # Forbidden alternative bindings
    code_lines = "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("//")
    )
    assert "ctypes" not in code_lines.lower(), "Must not use ctypes"
    assert "cffi" not in code_lines.lower(), "Must not use cffi"
    assert "cython" not in code_lines.lower(), "Must not use Cython"


def test_cargo_toml_does_not_use_linalg_libraries():
    """Cargo.toml must not pull in any external linear algebra crate."""
    assert CARGO_TOML.exists(), "Cargo.toml not found"
    content = CARGO_TOML.read_text()
    # Strip comments
    code_lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        code_lines.append(line)
    code_text = "\n".join(code_lines).lower()

    forbidden = (
        "ndarray",
        "ndarray-linalg",
        "nalgebra",
        "nalgebra-lapack",
        "lapack",
        "lapack-sys",
        "lapacke",
        "lapacke-sys",
        "blas",
        "blas-src",
        "cblas",
        "cblas-sys",
        "openblas-src",
        "openblas-sys",
        "intel-mkl-src",
        "intel-mkl-sys",
        "linfa-linalg",
        "peroxide",
        "argmin",
        "russell",
        "faer",
        "numpy",
    )
    for crate in forbidden:
        # Allow "blas" only if it's part of an allowed substring; check word boundary
        assert re.search(rf"\b{re.escape(crate)}\b", code_text) is None, (
            f"Cargo.toml must not depend on `{crate}`"
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
        for name in ("cholesky", "solve", "qr", "eigh", "svd", "lstsq", "expm",
                      "schur", "logm", "sqrtm", "signm", "solve_sylvester", "funm"):
            monkeypatch.setattr(scipy_linalg, name, _blocked, raising=False)

    a_svd = np.load("/app/fixtures/A_svd_tall.npy")
    u, s, vt = mod.svd(a_svd)
    assert _array64(u, 2).shape[0] == a_svd.shape[0]

    a_schur = np.load("/app/fixtures/A_schur_general.npy")
    T, Q = mod.schur(a_schur)
    assert _array64(T, 2).shape == a_schur.shape

    a_matlog = np.load("/app/fixtures/A_matlog_spd.npy")
    assert _array64(mod.matrix_log(a_matlog), 2).shape == a_matlog.shape

    a_sqrtm = np.load("/app/fixtures/A_sqrtm_spd.npy")
    assert _array64(mod.sqrtm(a_sqrtm), 2).shape == a_sqrtm.shape

    a_qz = np.load("/app/fixtures/A_qz1.npy")
    b_qz = np.load("/app/fixtures/B_qz1.npy")
    S, T_qz, Qq, Zz = mod.qz(a_qz, b_qz)
    assert _array64(S, 2).shape == a_qz.shape

    a_signm = np.load("/app/fixtures/A_signm1.npy")
    assert _array64(mod.signm(a_signm), 2).shape == a_signm.shape

    a_syl = np.load("/app/fixtures/A_syl1.npy")
    b_syl = np.load("/app/fixtures/B_syl1.npy")
    c_syl = np.load("/app/fixtures/C_syl1.npy")
    assert _array64(mod.solve_sylvester(a_syl, b_syl, c_syl), 2).shape == c_syl.shape

    a_eig = np.load("/app/fixtures/A_eig1.npy")
    wr, wi, vecs = mod.eig(a_eig)
    assert _array64(wr, 1).shape == (a_eig.shape[0],)

    T_ord = np.load("/app/fixtures/T_ordschur1.npy")
    Q_ord = np.load("/app/fixtures/Q_ordschur1.npy")
    sel = np.load("/app/fixtures/select_ordschur1.npy")
    T_new, Q_new = mod.ordschur(T_ord, Q_ord, sel)
    assert _array64(T_new, 2).shape == T_ord.shape

    a_mp = np.load("/app/fixtures/A_sqrtm_spd.npy")
    assert _array64(mod.matrix_power(a_mp, 0.5), 2).shape == a_mp.shape


def test_import_all_functions():
    mod = _import_module()

    for name in (
        "svd", "schur", "matrix_log", "sqrtm",
        "qz", "signm", "solve_sylvester", "eig",
        "ordschur", "matrix_power",
    ):
        assert hasattr(mod, name), f"Missing function: {name}"
        assert callable(getattr(mod, name)), f"{name} is not callable"


# ===================================================================
# Pipeline test
# ===================================================================


def test_numpy_pipeline_matches_references():
    _build_if_needed()
    module = _load_pipeline_module()
    cases = module.run_pipeline("rustlinalg")
    assert len(cases) >= 3

    for item in cases:
        assert item["svd_recon_max_abs"] < 1e-6
        assert item["schur_recon_max_abs"] < 1e-7
        assert item["schur_Q_orthogonality"] < 1e-10
        assert item["matlog_roundtrip_max_abs"] < 1e-6
        assert item["sqrtm_squared_max_abs"] < 1e-6
        assert item["qz_recon_A_max_abs"] < 1e-7
        assert item["qz_recon_B_max_abs"] < 1e-7
        assert item["qz_Q_orthogonality"] < 1e-10
        assert item["qz_Z_orthogonality"] < 1e-10
        assert item["signm_squared_max_abs"] < 1e-6
        assert item["sylvester_residual_max_abs"] < 1e-7
        assert item["eig_recon_max_abs"] < 1e-6
        assert item["ordschur_recon_max_abs"] < 1e-7
        assert item["ordschur_Q_orthogonality"] < 1e-10


# ===================================================================
# Per-function basic correctness
# ===================================================================


def test_svd_reconstruction():
    mod = _import_module()

    a = np.load("/app/fixtures/A_svd_tall.npy")
    u, s, vt = mod.svd(a)
    u = _array64(u, 2)
    s = _array64(s, 1)
    vt = _array64(vt, 2)
    m, n = a.shape
    k = min(m, n)

    assert u.shape == (m, m), f"U must be {m}x{m}, got {u.shape}"
    assert vt.shape == (n, n), f"Vt must be {n}x{n}, got {vt.shape}"
    assert s.shape == (k,)

    # Singular values must be non-negative and descending
    assert np.all(s >= -1e-12), f"Singular values must be non-negative: {s}"
    assert np.all(np.diff(s) <= 1e-12), f"Singular values must be descending: {s}"

    # U and Vt must be orthogonal
    np.testing.assert_allclose(u.T @ u, np.eye(m), atol=1e-10,
                                err_msg="U must be orthogonal")
    np.testing.assert_allclose(vt @ vt.T, np.eye(n), atol=1e-10,
                                err_msg="Vt must be orthogonal")

    # Reconstruction
    np.testing.assert_allclose(
        u[:, :k] @ np.diag(s) @ vt[:k, :], a, atol=1e-8
    )


def test_schur_reconstruction():
    mod = _import_module()

    A = np.load("/app/fixtures/A_schur_general.npy")
    T, Q = mod.schur(A)
    T = _array64(T, 2)
    Q = _array64(Q, 2)
    n = A.shape[0]

    np.testing.assert_allclose(Q.T @ Q, np.eye(n), atol=1e-10,
                                err_msg="Q must be orthogonal")
    np.testing.assert_allclose(Q @ T @ Q.T, A, atol=1e-8,
                                err_msg="Schur reconstruction must hold")

    # T must be quasi-upper-triangular: nothing nonzero below the first subdiagonal
    for i in range(2, n):
        for j in range(i - 1):
            assert abs(T[i, j]) < 1e-10, \
                f"T[{i},{j}]={T[i,j]} -- T must be quasi-upper-triangular"


def test_matrix_log_identity():
    mod = _import_module()

    for n in (2, 4, 6):
        eye = np.eye(n, dtype=np.float64)
        log_I = _array64(mod.matrix_log(eye), 2)
        np.testing.assert_allclose(log_I, np.zeros((n, n)), atol=1e-10)


def test_sqrtm_basic():
    mod = _import_module()

    A = np.load("/app/fixtures/A_sqrtm_spd.npy")
    B = _array64(mod.sqrtm(A), 2)
    np.testing.assert_allclose(B @ B, A, atol=1e-8)


def test_qz_reconstruction():
    mod = _import_module()

    A = np.load("/app/fixtures/A_qz1.npy")
    B = np.load("/app/fixtures/B_qz1.npy")
    S, T, Q, Z = mod.qz(A, B)
    S = _array64(S, 2)
    T = _array64(T, 2)
    Q = _array64(Q, 2)
    Z = _array64(Z, 2)
    n = A.shape[0]

    np.testing.assert_allclose(Q.T @ Q, np.eye(n), atol=1e-10)
    np.testing.assert_allclose(Z.T @ Z, np.eye(n), atol=1e-10)
    np.testing.assert_allclose(Q.T @ A @ Z, S, atol=1e-8)
    np.testing.assert_allclose(Q.T @ B @ Z, T, atol=1e-8)

    for i in range(1, n):
        for j in range(i):
            assert abs(T[i, j]) < 1e-10, f"T[{i},{j}] = {T[i,j]} not zero"


def test_signm_basic():
    mod = _import_module()

    A = np.load("/app/fixtures/A_signm1.npy")
    S = _array64(mod.signm(A), 2)
    n = A.shape[0]
    np.testing.assert_allclose(S @ S, np.eye(n), atol=1e-8)

    # Eigenvalues of sign(A) must all be +/-1 (not all 0 or all +1 etc.)
    eigs = np.linalg.eigvals(S)
    for e in eigs:
        assert abs(abs(e) - 1.0) < 1e-6, f"sign(A) eigenvalue {e} is not +/- 1"


def test_solve_sylvester_basic():
    mod = _import_module()

    A = np.load("/app/fixtures/A_syl1.npy")
    B = np.load("/app/fixtures/B_syl1.npy")
    C = np.load("/app/fixtures/C_syl1.npy")
    X = _array64(mod.solve_sylvester(A, B, C), 2)
    np.testing.assert_allclose(A @ X + X @ B, C, atol=1e-8)


def test_eig_basic():
    """A @ v = lambda * v, plus the eigenvalue set must match numpy."""
    mod = _import_module()

    A = np.load("/app/fixtures/A_eig1.npy")
    wr, wi, vecs = mod.eig(A)
    wr = _array64(wr, 1)
    wi = _array64(wi, 1)
    vecs = _array64(vecs, 2)
    n = A.shape[0]

    assert wr.shape == (n,)
    assert wi.shape == (n,)
    assert vecs.shape == (n, n)

    j = 0
    while j < n:
        if abs(wi[j]) < 1e-14:
            v = vecs[:, j]
            np.testing.assert_allclose(A @ v, wr[j] * v, atol=1e-8)
            j += 1
        else:
            vr = vecs[:, j]
            vi = vecs[:, j + 1]
            np.testing.assert_allclose(
                A @ vr, wr[j] * vr - wi[j] * vi, atol=1e-8
            )
            np.testing.assert_allclose(
                A @ vi, wr[j] * vi + wi[j] * vr, atol=1e-8
            )
            j += 2

    # Eigenvalue set must match numpy reference (catches "all zeros" gaming)
    eigs_ref = np.linalg.eigvals(A)
    eigs_ours = np.array([complex(r, i) for r, i in zip(wr, wi)])
    eigs_ref_sorted = np.array(sorted(eigs_ref, key=lambda x: (x.real, x.imag)))
    eigs_ours_sorted = np.array(sorted(eigs_ours, key=lambda x: (x.real, x.imag)))
    np.testing.assert_allclose(eigs_ours_sorted, eigs_ref_sorted, atol=1e-6)


def test_ordschur_basic():
    """Reordered Schur form: reconstruction holds AND selected eigenvalues moved."""
    mod = _import_module()

    A = np.load("/app/fixtures/A_ordschur1.npy")
    T_in = np.load("/app/fixtures/T_ordschur1.npy")
    Q_in = np.load("/app/fixtures/Q_ordschur1.npy")
    sel = np.load("/app/fixtures/select_ordschur1.npy")

    T_new, Q_new = mod.ordschur(T_in, Q_in, sel)
    T_new = _array64(T_new, 2)
    Q_new = _array64(Q_new, 2)
    n = A.shape[0]

    np.testing.assert_allclose(Q_new.T @ Q_new, np.eye(n), atol=1e-10)
    np.testing.assert_allclose(Q_new @ T_new @ Q_new.T, A, atol=1e-8)

    # T_new must still be quasi-upper-triangular
    for i in range(2, n):
        for j in range(i - 1):
            assert abs(T_new[i, j]) < 1e-10, \
                f"T_new[{i},{j}]={T_new[i,j]} -- must be quasi-upper-triangular"

    # Selected eigenvalues must actually appear in the top-left block
    n_sel = int(np.sum(np.asarray(sel, dtype=bool)))
    if n_sel > 0 and n_sel < n:
        eigs_orig = sorted(np.linalg.eigvals(T_in), key=lambda x: (x.real, x.imag))
        eigs_top = np.linalg.eigvals(T_new[:n_sel, :n_sel])
        eigs_bot = np.linalg.eigvals(T_new[n_sel:, n_sel:])
        eigs_combined = sorted(np.concatenate([eigs_top, eigs_bot]),
                                key=lambda x: (x.real, x.imag))
        np.testing.assert_allclose(np.array(eigs_combined),
                                     np.array(eigs_orig), atol=1e-6)


def test_matrix_power_basic():
    mod = _import_module()

    A = np.load("/app/fixtures/A_sqrtm_spd.npy")

    A_half = _array64(mod.matrix_power(A, 0.5), 2)
    np.testing.assert_allclose(A_half @ A_half, A, atol=1e-7)

    A_inv = _array64(mod.matrix_power(A, -1.0), 2)
    n = A.shape[0]
    np.testing.assert_allclose(A @ A_inv, np.eye(n), atol=1e-7)

    A_one = _array64(mod.matrix_power(A, 1.0), 2)
    np.testing.assert_allclose(A_one, A, atol=1e-10)


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
