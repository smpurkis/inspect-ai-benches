import importlib
import importlib.util
import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


FILES = Path("/app/files")
PYX_SRC = FILES / "cylinalg.pyx"


def _build_if_needed():
    so_files = list(FILES.glob("cylinalg*.so"))
    if not so_files:
        result = subprocess.run(
            [sys.executable, "setup_build.py", "build_ext", "--inplace"],
            capture_output=True, text=True, timeout=120, cwd=str(FILES),
        )
        if result.returncode != 0:
            pytest.fail(f"Build failed:\n{result.stderr[-3000:]}")


def _import_module():
    _build_if_needed()
    if "cylinalg" in sys.modules:
        del sys.modules["cylinalg"]
    return importlib.import_module("cylinalg")


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


def _assert_fresh_process_does_not_delegate(module_name):
    _build_if_needed()
    script = f'''
import importlib
import numpy as np
import numpy.linalg as numpy_linalg

def blocked(*args, **kwargs):
    raise AssertionError("candidate delegated to Python linalg")

modules = [np.linalg, numpy_linalg]
try:
    import scipy.linalg as scipy_linalg
    modules.append(scipy_linalg)
except Exception:
    pass
for module in modules:
    for name, value in vars(module).items():
        if not name.startswith("__") and callable(value):
            setattr(module, name, blocked)

mod = importlib.import_module({module_name!r})
a = np.load("/app/fixtures/A_svd_tall.npy")
assert np.asarray(mod.svd(a)[0]).shape[0] == a.shape[0]
a = np.load("/app/fixtures/A_schur_general.npy")
assert np.asarray(mod.schur(a)[0]).shape == a.shape
a = np.load("/app/fixtures/A_matlog_spd.npy")
assert np.asarray(mod.matrix_log(a)).shape == a.shape
a = np.load("/app/fixtures/A_sqrtm_spd.npy")
assert np.asarray(mod.sqrtm(a)).shape == a.shape
assert np.asarray(mod.matrix_power(a, 0.5)).shape == a.shape
a = np.load("/app/fixtures/A_qz1.npy")
b = np.load("/app/fixtures/B_qz1.npy")
assert np.asarray(mod.qz(a, b)[0]).shape == a.shape
a = np.load("/app/fixtures/A_signm1.npy")
assert np.asarray(mod.signm(a)).shape == a.shape
a = np.load("/app/fixtures/A_syl1.npy")
b = np.load("/app/fixtures/B_syl1.npy")
c = np.load("/app/fixtures/C_syl1.npy")
assert np.asarray(mod.solve_sylvester(a, b, c)).shape == c.shape
a = np.load("/app/fixtures/A_eig1.npy")
assert np.asarray(mod.eig(a)[0]).shape == (a.shape[0],)
t = np.load("/app/fixtures/T_ordschur1.npy")
q = np.load("/app/fixtures/Q_ordschur1.npy")
select = np.load("/app/fixtures/select_ordschur1.npy")
assert np.asarray(mod.ordschur(t, q, select)[0]).shape == t.shape
'''
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True,
        timeout=180, cwd=str(FILES),
    )
    assert result.returncode == 0, (
        "fresh-process anti-delegation check failed:\n"
        f"{result.stdout[-1000:]}\n{result.stderr[-3000:]}"
    )


def _schur_selection(T, select):
    T = np.asarray(T, dtype=np.float64)
    select = np.asarray(select, dtype=bool)
    scale = max(1.0, float(np.max(np.abs(T))))
    block_tol = 100.0 * np.finfo(np.float64).eps * scale
    selected = []
    i = 0
    while i < T.shape[0]:
        width = 2 if i + 1 < T.shape[0] and abs(T[i + 1, i]) > block_tol else 1
        if np.any(select[i:i + width]):
            selected.extend(np.linalg.eigvals(T[i:i + width, i:i + width]))
        i += width
    return np.asarray(selected, dtype=np.complex128), len(selected)


def _assert_eigenvalue_multiset(actual, expected, rtol=2e-7, atol=2e-9):
    remaining = list(np.asarray(actual, dtype=np.complex128))
    for target in np.asarray(expected, dtype=np.complex128):
        assert remaining, f"missing selected eigenvalue {target}"
        index = min(range(len(remaining)), key=lambda j: abs(remaining[j] - target))
        candidate = remaining.pop(index)
        limit = atol + rtol * max(1.0, abs(target))
        assert abs(candidate - target) <= limit, (
            f"selected eigenvalue {target} not in leading block; closest was {candidate}"
        )
    assert not remaining, f"unexpected leading-block eigenvalues: {remaining}"


# ===================================================================
# Cross-cutting tests
# ===================================================================


def test_hidden_pipeline_stricter_thresholds():
    _build_if_needed()
    module = _load_pipeline_module()
    cases = module.run_pipeline("cylinalg")

    for item in cases:
        assert item["svd_recon_max_abs"] < 5e-8, \
            f"SVD reconstruction {item['svd_recon_max_abs']:.2e} >= 5e-8"
        assert item["schur_recon_max_abs"] < 5e-8, \
            f"Schur reconstruction {item['schur_recon_max_abs']:.2e} >= 5e-8"
        assert item["schur_Q_orthogonality"] < 5e-11, \
            f"Schur Q orthogonality {item['schur_Q_orthogonality']:.2e} >= 5e-11"
        assert item["matlog_roundtrip_max_abs"] < 5e-8, \
            f"Matrix log roundtrip {item['matlog_roundtrip_max_abs']:.2e} >= 5e-8"
        assert item["sqrtm_squared_max_abs"] < 5e-8, \
            f"Sqrtm squared {item['sqrtm_squared_max_abs']:.2e} >= 5e-8"
        assert item["qz_recon_A_max_abs"] < 5e-8, \
            f"QZ recon A {item['qz_recon_A_max_abs']:.2e} >= 5e-8"
        assert item["qz_recon_B_max_abs"] < 5e-8, \
            f"QZ recon B {item['qz_recon_B_max_abs']:.2e} >= 5e-8"
        assert item["qz_Q_orthogonality"] < 5e-11, \
            f"QZ Q orthogonality {item['qz_Q_orthogonality']:.2e} >= 5e-11"
        assert item["qz_Z_orthogonality"] < 5e-11, \
            f"QZ Z orthogonality {item['qz_Z_orthogonality']:.2e} >= 5e-11"
        assert item["signm_squared_max_abs"] < 5e-8, \
            f"Signm squared {item['signm_squared_max_abs']:.2e} >= 5e-8"
        assert item["sylvester_residual_max_abs"] < 5e-8, \
            f"Sylvester residual {item['sylvester_residual_max_abs']:.2e} >= 5e-8"
        assert item["eig_recon_max_abs"] < 5e-8, \
            f"Eig reconstruction {item['eig_recon_max_abs']:.2e} >= 5e-8"
        assert item["ordschur_recon_max_abs"] < 5e-8, \
            f"Ordschur reconstruction {item['ordschur_recon_max_abs']:.2e} >= 5e-8"
        assert item["ordschur_Q_orthogonality"] < 5e-11, \
            f"Ordschur Q orthogonality {item['ordschur_Q_orthogonality']:.2e} >= 5e-11"


def test_hidden_error_handling():
    mod = _import_module()

    # Non-square matrix for square-only functions
    rect = np.zeros((3, 4), dtype=np.float64)
    with pytest.raises(Exception):
        mod.schur(rect)
    with pytest.raises(Exception):
        mod.matrix_log(rect)
    with pytest.raises(Exception):
        mod.sqrtm(rect)
    with pytest.raises(Exception):
        mod.signm(rect)
    with pytest.raises(Exception):
        mod.eig(rect)

    # Mismatched dimensions for qz
    a5 = np.zeros((5, 5), dtype=np.float64)
    a4 = np.zeros((4, 4), dtype=np.float64)
    with pytest.raises(Exception):
        mod.qz(a5, a4)

    # Mismatched dimensions for solve_sylvester
    with pytest.raises(Exception):
        mod.solve_sylvester(
            np.zeros((3, 3), dtype=np.float64),
            np.zeros((4, 4), dtype=np.float64),
            np.zeros((3, 3), dtype=np.float64),  # should be 3x4
        )


def test_hidden_source_and_runtime_do_not_delegate():
    source = PYX_SRC.read_text()
    code_lines = []
    in_docstring = False
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(('"""', "'''")):
            if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                continue
            in_docstring = not in_docstring
            continue
        if not in_docstring and not stripped.startswith("#"):
            code_lines.append(line.split("#", 1)[0])
    code_text = "\n".join(code_lines)
    forbidden = (
        r"\.\s*linalg\b",
        r"from\s+(?:numpy|scipy)\s+import\s+linalg",
        r"\bimport\s+scipy\b",
        r"\b(?:__import__|importlib)\b",
        r"\bgetattr\s*\([^,\n]+,\s*['\"]linalg['\"]",
        r"\bpyo3\b",
    )
    for pattern in forbidden:
        assert re.search(pattern, code_text) is None, (
            f"cylinalg.pyx contains forbidden delegation pattern: {pattern}"
        )

    _assert_fresh_process_does_not_delegate("cylinalg")


def test_hidden_cython_source_build_and_api_contract():
    source = PYX_SRC.read_text()
    assert len(source) > 2000, "cylinalg.pyx is suspiciously short"
    assert "STUB" not in source, "cylinalg.pyx still contains a STUB placeholder"
    assert "cimport" in source or "cdef" in source, "Cython features are required"

    code_text = "\n".join(
        line.split("#", 1)[0]
        for line in source.splitlines()
        if not line.strip().startswith("#")
    ).lower()
    for alternative in ("import ctypes", "cffi", "pyo3"):
        assert alternative not in code_text, f"forbidden alternative binding: {alternative}"

    generated = FILES / "cylinalg.c"
    if generated.exists():
        generated_source = generated.read_text()
        assert "Cython" in generated_source or "cython" in generated_source

    module = _import_module()
    for name in (
        "svd", "schur", "matrix_log", "sqrtm", "qz", "signm",
        "solve_sylvester", "eig", "ordschur", "matrix_power",
    ):
        assert callable(getattr(module, name, None)), f"missing callable {name}"


# ===================================================================
# SVD hidden tests (4)
# ===================================================================


def test_hidden_svd_50x30_tight_tolerance():
    """50x30 random matrix with tight reconstruction and orthogonality."""
    mod = _import_module()

    rng = np.random.default_rng(4040)
    A = rng.standard_normal((50, 30)).astype(np.float64)
    u, sig, vt = mod.svd(A)
    u = _array64(u, 2)
    sig = _array64(sig, 1)
    vt = _array64(vt, 2)
    m, n = A.shape
    k = min(m, n)

    assert u.shape == (m, m)
    assert sig.shape == (k,)
    assert vt.shape == (n, n)
    assert np.all(sig >= -1e-14), f"Negative singular values: {sig}"
    assert np.all(np.diff(sig) <= 1e-12), f"Not descending: {sig}"

    np.testing.assert_allclose(u.T @ u, np.eye(m), atol=1e-12)
    np.testing.assert_allclose(vt @ vt.T, np.eye(n), atol=1e-12)
    np.testing.assert_allclose(
        u[:, :k] @ np.diag(sig) @ vt[:k, :], A, atol=1e-8
    )


@pytest.mark.parametrize(
    "m,n,condition,seed",
    [(9, 6, 1e2, 5050), (12, 12, 1e6, 5051), (14, 10, 1e10, 5052)],
)
def test_hidden_svd_generated_condition_numbers(m, n, condition, seed):
    """Deterministic generated matrices spanning mild to severe conditioning."""
    mod = _import_module()

    rng = np.random.default_rng(seed)
    U0, _ = np.linalg.qr(rng.standard_normal((m, m)))
    V0, _ = np.linalg.qr(rng.standard_normal((n, n)))
    k = min(m, n)
    svals = np.geomspace(1.0, 1.0 / condition, k)
    A = (U0[:, :k] @ np.diag(svals) @ V0[:k, :]).astype(np.float64)

    u, sig, vt = mod.svd(A)
    u = _array64(u, 2)
    sig = _array64(sig, 1)
    vt = _array64(vt, 2)
    observed_condition = sig[0] / sig[-1]
    condition_rtol = max(5e-6, 200.0 * np.finfo(float).eps * condition)
    np.testing.assert_allclose(observed_condition, condition, rtol=condition_rtol)

    reconstruction = u[:, :k] @ np.diag(sig) @ vt[:k, :]
    relative_residual = np.linalg.norm(reconstruction - A) / np.linalg.norm(A)
    residual_limit = max(
        2e-8,
        500.0 * np.finfo(float).eps * max(m, n) * math.sqrt(condition),
    )
    assert relative_residual < residual_limit, (
        f"relative reconstruction residual {relative_residual:.3e} "
        f"exceeds {residual_limit:.3e} at condition {condition:.1e}"
    )
    np.testing.assert_allclose(u.T @ u, np.eye(m), atol=1e-10)
    np.testing.assert_allclose(vt @ vt.T, np.eye(n), atol=1e-10)


def test_hidden_svd_rank_deficient():
    """Rank-3 matrix of size 6x6: 3 near-zero singular values."""
    mod = _import_module()

    rng = np.random.default_rng(60031)
    U_part = rng.standard_normal((6, 3))
    V_part = rng.standard_normal((3, 6))
    A = (U_part @ V_part).astype(np.float64)

    u, sig, vt = mod.svd(A)
    u = _array64(u, 2)
    sig = _array64(sig, 1)
    vt = _array64(vt, 2)

    assert sig.shape == (6,)
    assert np.all(sig[:3] > 0.01), f"First 3 singular values should be positive, got {sig[:3]}"
    assert np.all(sig[3:] < 1e-6), \
        f"Rank-3 matrix should have 3 near-zero singular values, got {sig[3:]}"

    np.testing.assert_allclose(
        u @ np.diag(sig) @ vt, A, atol=1e-8,
        err_msg="SVD reconstruction failed for rank-deficient matrix"
    )


def test_hidden_svd_trivial_sizes():
    """SVD of 1x1, 1x5, 5x1 matrices."""
    mod = _import_module()

    # 1x1
    A1 = np.array([[3.7]], dtype=np.float64)
    u, sig, vt = mod.svd(A1)
    u = _array64(u, 2)
    sig = _array64(sig, 1)
    vt = _array64(vt, 2)
    assert sig.shape == (1,)
    np.testing.assert_allclose(sig[0], 3.7, atol=1e-12)
    np.testing.assert_allclose(u @ np.diag(sig) @ vt, A1, atol=1e-12)

    # 1x5
    A15 = np.array([[1.0, 2.0, 3.0, 4.0, 5.0]], dtype=np.float64)
    u, sig, vt = mod.svd(A15)
    u = _array64(u, 2)
    sig = _array64(sig, 1)
    vt = _array64(vt, 2)
    k = 1
    np.testing.assert_allclose(
        u[:, :k] @ np.diag(sig) @ vt[:k, :], A15, atol=1e-10
    )

    # 5x1
    A51 = np.array([[1.0], [2.0], [3.0], [4.0], [5.0]], dtype=np.float64)
    u, sig, vt = mod.svd(A51)
    u = _array64(u, 2)
    sig = _array64(sig, 1)
    vt = _array64(vt, 2)
    k = 1
    np.testing.assert_allclose(
        u[:, :k] @ np.diag(sig) @ vt[:k, :], A51, atol=1e-10
    )


# ===================================================================
# Schur hidden tests (4)
# ===================================================================


def test_hidden_schur_very_large_60x60():
    """60x60 random matrix Schur decomposition."""
    mod = _import_module()

    rng = np.random.default_rng(66666)
    n = 60
    A = rng.standard_normal((n, n)).astype(np.float64)
    T, Q = mod.schur(A)
    T = _array64(T, 2)
    Q = _array64(Q, 2)

    np.testing.assert_allclose(Q.T @ Q, np.eye(n), atol=1e-9)
    np.testing.assert_allclose(Q @ T @ Q.T, A, atol=1e-6)


def test_hidden_schur_complex_eigenvalues():
    mod = _import_module()

    A = np.load("/app/fixtures/A_schur_complex.npy")
    T, Q = mod.schur(A)
    T = _array64(T, 2)
    Q = _array64(Q, 2)
    n = A.shape[0]

    np.testing.assert_allclose(Q.T @ Q, np.eye(n), atol=1e-10)
    np.testing.assert_allclose(Q @ T @ Q.T, A, atol=1e-8)

    # Verify at least one 2x2 block exists (complex eigenvalues)
    found_2x2 = False
    i = 0
    while i < n - 1:
        if abs(T[i + 1, i]) > 1e-10:
            found_2x2 = True
            block = T[i:i + 2, i:i + 2]
            eig_block = np.linalg.eigvals(block)
            assert np.any(np.abs(eig_block.imag) > 1e-8)
            if i + 2 < n:
                assert abs(T[i + 2, i + 1]) < 1e-10
            i += 2
        else:
            i += 1
    assert found_2x2


def test_hidden_schur_near_defective():
    mod = _import_module()

    rng = np.random.default_rng(31415)
    n = 10
    Q_rand, _ = np.linalg.qr(rng.standard_normal((n, n)))
    eigs = np.array([1.0 + i * 1e-8 for i in range(6)] + [5.0, -2.0, 3.0, -1.0])
    A = (Q_rand @ np.diag(eigs) @ Q_rand.T).astype(np.float64)

    T, Q = mod.schur(A)
    T = _array64(T, 2)
    Q = _array64(Q, 2)

    np.testing.assert_allclose(Q.T @ Q, np.eye(n), atol=1e-8)
    np.testing.assert_allclose(Q @ T @ Q.T, A, atol=1e-5)


def test_hidden_schur_30x30_strict():
    """30x30 random matrix with strict tolerances."""
    mod = _import_module()

    rng = np.random.default_rng(99887)
    n = 30
    A = rng.standard_normal((n, n)).astype(np.float64)
    T, Q = mod.schur(A)
    T = _array64(T, 2)
    Q = _array64(Q, 2)

    np.testing.assert_allclose(Q.T @ Q, np.eye(n), atol=1e-11)
    np.testing.assert_allclose(Q @ T @ Q.T, A, atol=1e-8)

    # Verify quasi-upper-triangular: no nonzero entries below first subdiagonal
    for i in range(2, n):
        for j in range(i - 1):
            assert abs(T[i, j]) < 1e-10, \
                f"T[{i},{j}] = {T[i,j]} -- not quasi-upper-triangular"


# ===================================================================
# Matrix log hidden tests (4)
# ===================================================================


def test_hidden_matrix_log_roundtrip():
    mod = _import_module()
    from scipy.linalg import expm

    A_spd = np.load("/app/fixtures/A_matlog_spd.npy")
    log_A = _array64(mod.matrix_log(A_spd), 2)
    exp_log_A = expm(log_A)
    np.testing.assert_allclose(exp_log_A, A_spd, rtol=1e-5, atol=1e-6)

    # Backward: log(exp(B)) = B for small-norm B
    rng = np.random.default_rng(12345)
    B = rng.standard_normal((5, 5)).astype(np.float64) * 0.1
    exp_B = expm(B)
    log_exp_B = _array64(mod.matrix_log(exp_B), 2)
    np.testing.assert_allclose(log_exp_B, B, rtol=1e-4, atol=1e-5)


def test_hidden_matrix_log_complex_eigenvalues():
    mod = _import_module()
    from scipy.linalg import expm

    A = np.load("/app/fixtures/A_matlog_complex.npy")
    log_A = _array64(mod.matrix_log(A), 2)
    exp_log_A = expm(log_A)
    np.testing.assert_allclose(exp_log_A, A, rtol=1e-4, atol=1e-5)
    assert np.all(np.isfinite(log_A))


def test_hidden_matrix_log_negative_eigenvalue_error():
    mod = _import_module()

    A_neg = np.diag([2.0, -1.0, 3.0]).astype(np.float64)
    with pytest.raises(Exception):
        mod.matrix_log(A_neg)

    A_neg2 = np.array([
        [-2.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 3.0],
    ], dtype=np.float64)
    with pytest.raises(Exception):
        mod.matrix_log(A_neg2)


def test_hidden_matrix_log_20x20_spd():
    """20x20 SPD matrix -- large-scale log roundtrip."""
    mod = _import_module()
    from scipy.linalg import expm

    rng = np.random.default_rng(70707)
    n = 20
    M = rng.standard_normal((n, n))
    A = (M @ M.T + 0.5 * np.eye(n)).astype(np.float64)

    log_A = _array64(mod.matrix_log(A), 2)
    assert np.all(np.isfinite(log_A)), "matrix_log returned non-finite values"
    exp_log_A = expm(log_A)
    np.testing.assert_allclose(exp_log_A, A, rtol=1e-5, atol=1e-6)

    # log(A) should be symmetric for SPD input
    np.testing.assert_allclose(log_A, log_A.T, atol=1e-8)


# ===================================================================
# Matrix square root hidden tests (4)
# ===================================================================


def test_hidden_sqrtm_complex_eigenvalues():
    """Matrix with complex eigenvalue pairs."""
    mod = _import_module()

    A = np.load("/app/fixtures/A_sqrtm_complex.npy")
    B = _array64(mod.sqrtm(A), 2)
    np.testing.assert_allclose(B @ B, A, atol=1e-7)
    assert np.all(np.isfinite(B))


def test_hidden_sqrtm_negative_eigenvalue_error():
    """Matrix with negative real eigenvalue should raise."""
    mod = _import_module()

    A_neg = np.diag([2.0, -1.0, 3.0]).astype(np.float64)
    with pytest.raises(Exception):
        mod.sqrtm(A_neg)


def test_hidden_sqrtm_30x30_spd():
    """30x30 SPD matrix -- sqrt(A) @ sqrt(A) = A with tight tolerance."""
    mod = _import_module()

    rng = np.random.default_rng(80808)
    n = 30
    M = rng.standard_normal((n, n))
    A = (M @ M.T + 0.3 * np.eye(n)).astype(np.float64)

    B = _array64(mod.sqrtm(A), 2)
    np.testing.assert_allclose(B @ B, A, atol=1e-7)

    # sqrt of SPD should itself be SPD (symmetric positive definite)
    np.testing.assert_allclose(B, B.T, atol=1e-8)
    eigvals_B = np.linalg.eigvalsh(B)
    assert np.all(eigvals_B > -1e-10), \
        f"sqrt of SPD should have non-negative eigenvalues, got min={eigvals_B.min()}"


def test_hidden_sqrtm_identity():
    """sqrt(I) = I for various sizes."""
    mod = _import_module()

    for n in (1, 5, 12):
        I = np.eye(n, dtype=np.float64)
        B = _array64(mod.sqrtm(I), 2)
        np.testing.assert_allclose(B, I, atol=1e-12)


# ===================================================================
# QZ decomposition hidden tests (4)
# ===================================================================


def test_hidden_qz_reconstruction_stress():
    """8x8 pair reconstruction."""
    mod = _import_module()

    A = np.load("/app/fixtures/A_qz3.npy")
    B = np.load("/app/fixtures/B_qz3.npy")
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

    # T upper triangular
    for i in range(1, n):
        for j in range(i):
            assert abs(T[i, j]) < 1e-10


def test_hidden_qz_near_singular_b():
    """Near-singular B -- tests infinite eigenvalue handling."""
    mod = _import_module()

    A = np.load("/app/fixtures/A_qz2.npy")
    B = np.load("/app/fixtures/B_qz2.npy")
    S, T, Q, Z = mod.qz(A, B)
    S = _array64(S, 2)
    T = _array64(T, 2)
    Q = _array64(Q, 2)
    Z = _array64(Z, 2)
    n = A.shape[0]

    np.testing.assert_allclose(Q.T @ Q, np.eye(n), atol=1e-9)
    np.testing.assert_allclose(Z.T @ Z, np.eye(n), atol=1e-9)
    np.testing.assert_allclose(Q.T @ A @ Z, S, atol=1e-7)
    np.testing.assert_allclose(Q.T @ B @ Z, T, atol=1e-7)


def test_hidden_qz_30x30():
    """30x30 random pair with tight tolerances."""
    mod = _import_module()

    rng = np.random.default_rng(30303)
    n = 30
    A = rng.standard_normal((n, n)).astype(np.float64)
    B = rng.standard_normal((n, n)).astype(np.float64)

    S, T, Q, Z = mod.qz(A, B)
    S = _array64(S, 2)
    T = _array64(T, 2)
    Q = _array64(Q, 2)
    Z = _array64(Z, 2)

    np.testing.assert_allclose(Q.T @ Q, np.eye(n), atol=1e-10)
    np.testing.assert_allclose(Z.T @ Z, np.eye(n), atol=1e-10)
    np.testing.assert_allclose(Q.T @ A @ Z, S, atol=1e-7)
    np.testing.assert_allclose(Q.T @ B @ Z, T, atol=1e-7)

    # T must be upper triangular
    for i in range(1, n):
        for j in range(i):
            assert abs(T[i, j]) < 1e-10, f"T[{i},{j}] = {T[i,j]}"


def test_hidden_qz_identity_b():
    """QZ with B = I should reduce to ordinary Schur."""
    mod = _import_module()

    rng = np.random.default_rng(12321)
    n = 10
    A = rng.standard_normal((n, n)).astype(np.float64)
    B = np.eye(n, dtype=np.float64)

    S, T, Q, Z = mod.qz(A, B)
    S = _array64(S, 2)
    T = _array64(T, 2)
    Q = _array64(Q, 2)
    Z = _array64(Z, 2)

    np.testing.assert_allclose(Q.T @ Q, np.eye(n), atol=1e-10)
    np.testing.assert_allclose(Z.T @ Z, np.eye(n), atol=1e-10)
    np.testing.assert_allclose(Q.T @ A @ Z, S, atol=1e-8)
    np.testing.assert_allclose(Q.T @ B @ Z, T, atol=1e-8)

    # T should be close to identity (since B = I)
    np.testing.assert_allclose(T, np.eye(n), atol=1e-8)


# ===================================================================
# Matrix sign function hidden tests (4)
# ===================================================================


def test_hidden_signm_squared_identity():
    """sign(A) @ sign(A) = I for various matrices."""
    mod = _import_module()

    for name in ("A_signm1.npy", "A_signm_real.npy", "A_signm_complex.npy"):
        A = np.load(f"/app/fixtures/{name}")
        S = _array64(mod.signm(A), 2)
        n = A.shape[0]
        np.testing.assert_allclose(S @ S, np.eye(n), atol=1e-7)


def test_hidden_signm_eigenvalue_property():
    """Eigenvalues of sign(A) should be +1 or -1."""
    mod = _import_module()

    A = np.load("/app/fixtures/A_signm_real.npy")
    S = _array64(mod.signm(A), 2)
    eigs = np.linalg.eigvals(S)
    for e in eigs:
        assert abs(abs(e) - 1.0) < 1e-6, f"Eigenvalue {e} not +/- 1"


def test_hidden_signm_20x20():
    """20x20 random matrix with no purely imaginary eigenvalues."""
    mod = _import_module()

    rng = np.random.default_rng(20202)
    n = 20
    # Ensure no eigenvalue on imaginary axis by adding a diagonal shift
    A = (rng.standard_normal((n, n)) + 2.0 * np.eye(n)).astype(np.float64)

    S = _array64(mod.signm(A), 2)
    np.testing.assert_allclose(S @ S, np.eye(n), atol=1e-6)

    # Eigenvalues should all be +/-1
    eigs = np.linalg.eigvals(S)
    for e in eigs:
        assert abs(abs(e) - 1.0) < 1e-5, f"Eigenvalue {e} not +/- 1"


def test_hidden_signm_imaginary_axis_error():
    """Matrix with eigenvalue on imaginary axis should raise."""
    mod = _import_module()

    # Skew-symmetric matrix has purely imaginary eigenvalues
    A = np.array([
        [0.0, 1.0, 0.0],
        [-1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
    ], dtype=np.float64)
    with pytest.raises(Exception):
        mod.signm(A)


# ===================================================================
# Sylvester equation hidden tests (3)
# ===================================================================


def test_hidden_sylvester_exact():
    """Check against scipy reference solution."""
    mod = _import_module()

    A = np.load("/app/fixtures/A_syl1.npy")
    B = np.load("/app/fixtures/B_syl1.npy")
    C = np.load("/app/fixtures/C_syl1.npy")
    X_ref = np.load("/app/fixtures/X_syl1_ref.npy")

    X = _array64(mod.solve_sylvester(A, B, C), 2)
    np.testing.assert_allclose(X, X_ref, atol=1e-8)
    np.testing.assert_allclose(A @ X + X @ B, C, atol=1e-8)


def test_hidden_sylvester_rectangular():
    """A is 4x4, B is 6x6, C is 4x6."""
    mod = _import_module()

    A = np.load("/app/fixtures/A_syl2.npy")
    B = np.load("/app/fixtures/B_syl2.npy")
    C = np.load("/app/fixtures/C_syl2.npy")

    X = _array64(mod.solve_sylvester(A, B, C), 2)
    assert X.shape == (4, 6)
    np.testing.assert_allclose(A @ X + X @ B, C, atol=1e-8)


def test_hidden_sylvester_20x20():
    """20x20 system with tight residual check."""
    mod = _import_module()

    rng = np.random.default_rng(20200)
    n = 20
    # Ensure well-separated spectra for A and -B
    A = rng.standard_normal((n, n)).astype(np.float64) + 3.0 * np.eye(n)
    B = rng.standard_normal((n, n)).astype(np.float64) - 3.0 * np.eye(n)
    C = rng.standard_normal((n, n)).astype(np.float64)

    X = _array64(mod.solve_sylvester(A, B, C), 2)
    np.testing.assert_allclose(A @ X + X @ B, C, atol=1e-7)

    # Cross-check with scipy
    from scipy.linalg import solve_sylvester as sp_solve_sylvester
    X_ref = sp_solve_sylvester(A, B, C)
    np.testing.assert_allclose(X, X_ref, atol=1e-6)


# ===================================================================
# Nonsymmetric eigenvalue hidden tests (4)
# ===================================================================


def test_hidden_eig_complex_pairs():
    """Matrix known to have complex conjugate eigenvalue pairs."""
    mod = _import_module()

    A = np.load("/app/fixtures/A_eig1.npy")
    wr, wi, vecs = mod.eig(A)
    wr = _array64(wr, 1)
    wi = _array64(wi, 1)
    vecs = _array64(vecs, 2)
    n = A.shape[0]

    # Check complex conjugate symmetry: if (a + bi) then (a - bi)
    complex_found = False
    j = 0
    while j < n:
        if abs(wi[j]) > 1e-10:
            complex_found = True
            assert j + 1 < n, "Complex eigenvalue without conjugate pair"
            assert abs(wr[j] - wr[j + 1]) < 1e-10, "Real parts should match"
            assert abs(wi[j] + wi[j + 1]) < 1e-10, "Imaginary parts should be conjugate"
            j += 2
        else:
            j += 1

    # Verify reconstruction for all eigenvalues
    j = 0
    while j < n:
        if abs(wi[j]) < 1e-14:
            v = vecs[:, j]
            np.testing.assert_allclose(A @ v, wr[j] * v, atol=1e-7)
            j += 1
        else:
            vr = vecs[:, j]
            vi = vecs[:, j + 1]
            np.testing.assert_allclose(
                A @ vr, wr[j] * vr - wi[j] * vi, atol=1e-7
            )
            np.testing.assert_allclose(
                A @ vi, wr[j] * vi + wi[j] * vr, atol=1e-7
            )
            j += 2


def test_hidden_eig_all_real():
    """Symmetric matrix should give all real eigenvalues."""
    mod = _import_module()

    A = np.load("/app/fixtures/A_eig_real.npy")
    wr, wi, vecs = mod.eig(A)
    wr = _array64(wr, 1)
    wi = _array64(wi, 1)
    vecs = _array64(vecs, 2)

    # All imaginary parts should be zero
    np.testing.assert_allclose(wi, 0.0, atol=1e-10)

    # Eigenvalues should match numpy
    eigs_ref = sorted(np.linalg.eigvalsh(A))
    eigs_ours = sorted(wr)
    np.testing.assert_allclose(eigs_ours, eigs_ref, atol=1e-8)


def test_hidden_eig_20x20():
    """20x20 general matrix with full reconstruction check."""
    mod = _import_module()

    rng = np.random.default_rng(20201)
    n = 20
    A = rng.standard_normal((n, n)).astype(np.float64)
    wr, wi, vecs = mod.eig(A)
    wr = _array64(wr, 1)
    wi = _array64(wi, 1)
    vecs = _array64(vecs, 2)

    # Reconstruction check
    j = 0
    while j < n:
        if abs(wi[j]) < 1e-14:
            v = vecs[:, j]
            np.testing.assert_allclose(A @ v, wr[j] * v, atol=1e-6)
            j += 1
        else:
            vr = vecs[:, j]
            vi = vecs[:, j + 1]
            np.testing.assert_allclose(
                A @ vr, wr[j] * vr - wi[j] * vi, atol=1e-6
            )
            np.testing.assert_allclose(
                A @ vi, wr[j] * vi + wi[j] * vr, atol=1e-6
            )
            j += 2

    # Eigenvalues should match numpy reference
    eigs_ref = np.linalg.eigvals(A)
    eigs_ours = np.array([complex(r, i) for r, i in zip(wr, wi)])
    eigs_ref_sorted = sorted(eigs_ref, key=lambda x: (x.real, x.imag))
    eigs_ours_sorted = sorted(eigs_ours, key=lambda x: (x.real, x.imag))
    np.testing.assert_allclose(
        np.array(eigs_ours_sorted), np.array(eigs_ref_sorted), atol=1e-6
    )


def test_hidden_eig_near_defective():
    """Matrix with clustered eigenvalues."""
    mod = _import_module()

    A = np.load("/app/fixtures/A_eig_neardef.npy")
    wr, wi, vecs = mod.eig(A)
    wr = _array64(wr, 1)
    wi = _array64(wi, 1)
    n = A.shape[0]

    # Eigenvalues should still be close to the reference
    eigs_ref = np.linalg.eigvals(A)
    eigs_ours = np.array([complex(r, i) for r, i in zip(wr, wi)])
    eigs_ref_sorted = sorted(eigs_ref, key=lambda x: (x.real, x.imag))
    eigs_ours_sorted = sorted(eigs_ours, key=lambda x: (x.real, x.imag))
    np.testing.assert_allclose(
        np.array(eigs_ours_sorted), np.array(eigs_ref_sorted), atol=1e-4
    )


# ===================================================================
# Ordered Schur hidden tests (4)
# ===================================================================


def test_hidden_ordschur_reconstruction():
    """Reordered Schur form still satisfies A = Q @ T @ Q^T."""
    mod = _import_module()

    T_in = np.load("/app/fixtures/T_ordschur1.npy")
    Q_in = np.load("/app/fixtures/Q_ordschur1.npy")
    A = Q_in @ T_in @ Q_in.T
    n = T_in.shape[0]
    sel = [True, False, True, False, True, False]

    T_new, Q_new = mod.ordschur(T_in, Q_in, sel)
    T_new = _array64(T_new, 2)
    Q_new = _array64(Q_new, 2)

    np.testing.assert_allclose(Q_new.T @ Q_new, np.eye(n), atol=1e-10)
    np.testing.assert_allclose(Q_new @ T_new @ Q_new.T, A, atol=1e-8)


def test_hidden_ordschur_selected_eigenvalues_moved():
    """Verify selected eigenvalues actually appear in the top-left block."""
    mod = _import_module()

    T = np.load("/app/fixtures/T_ordschur1.npy")
    Q = np.load("/app/fixtures/Q_ordschur1.npy")
    select = [True, False, True, False, True, False]
    expected, leading_size = _schur_selection(T, select)

    T_new, Q_new = mod.ordschur(T, Q, select)
    T_new = _array64(T_new, 2)

    actual = np.linalg.eigvals(T_new[:leading_size, :leading_size])
    _assert_eigenvalue_multiset(actual, expected)


def test_hidden_ordschur_complex_block_swap():
    """Selecting one member moves its whole conjugate 2x2 block to the front."""
    mod = _import_module()

    T = np.array([
        [3.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, -4.0, 0.0],
        [0.0, 4.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, -2.0],
    ])
    Q = np.eye(4)
    select = [False, True, False, False]
    expected, leading_size = _schur_selection(T, select)
    assert leading_size == 2

    T_new, Q_new = mod.ordschur(T, Q, select)
    T_new = _array64(T_new, 2)
    Q_new = _array64(Q_new, 2)

    np.testing.assert_allclose(Q_new @ T_new @ Q_new.T, T, atol=1e-8)
    np.testing.assert_allclose(Q_new.T @ Q_new, np.eye(4), atol=1e-10)
    actual = np.linalg.eigvals(T_new[:leading_size, :leading_size])
    _assert_eigenvalue_multiset(actual, expected)


def test_hidden_ordschur_15x15():
    """15x15 matrix reordering."""
    mod = _import_module()

    T = np.load("/app/fixtures/T_ordschur3.npy")
    Q = np.load("/app/fixtures/Q_ordschur3.npy")
    A = Q @ T @ Q.T
    n = T.shape[0]

    # Select roughly half
    select = [bool(i % 2 == 0) for i in range(n)]
    T_new, Q_new = mod.ordschur(T, Q, select)
    T_new = _array64(T_new, 2)
    Q_new = _array64(Q_new, 2)

    np.testing.assert_allclose(Q_new @ T_new @ Q_new.T, A, atol=1e-7,
        err_msg="Ordschur reconstruction failed for 15x15 at atol=1e-7")
    np.testing.assert_allclose(Q_new.T @ Q_new, np.eye(n), atol=1e-9,
        err_msg="Ordschur Q not orthogonal for 15x15")


# ===================================================================
# Matrix power hidden tests (3)
# ===================================================================


def test_hidden_matrix_power_third():
    """A^(1/3) cubed should give A."""
    mod = _import_module()

    A = np.load("/app/fixtures/A_sqrtm_spd.npy")
    A_third = _array64(mod.matrix_power(A, 1.0 / 3.0), 2)
    np.testing.assert_allclose(A_third @ A_third @ A_third, A, atol=1e-5)


def test_hidden_matrix_power_fractional():
    """A^0.7 @ A^0.3 should equal A."""
    mod = _import_module()

    A = np.load("/app/fixtures/A_sqrtm_spd.npy")
    A_07 = _array64(mod.matrix_power(A, 0.7), 2)
    A_03 = _array64(mod.matrix_power(A, 0.3), 2)
    # A^0.7 @ A^0.3 should equal A
    np.testing.assert_allclose(A_07 @ A_03, A, atol=1e-5)


def test_hidden_matrix_power_complex_eigenvalues():
    """Matrix with complex eigenvalues (positive real parts), A^0.5."""
    mod = _import_module()

    A = np.load("/app/fixtures/A_sqrtm_complex.npy")
    A_half = _array64(mod.matrix_power(A, 0.5), 2)
    np.testing.assert_allclose(A_half @ A_half, A, atol=1e-6)


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
