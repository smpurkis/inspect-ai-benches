"""Test suite for rustlinalg — run with: pytest /app/tests/test_rustlinalg.py -v"""

import re
from pathlib import Path

import numpy as np
import pytest


def _array64(value, ndim: int | None = None) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    if ndim is not None:
        assert arr.ndim == ndim, f"expected {ndim}D output, got shape {arr.shape}"
    return arr


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

    for name in ("cholesky", "solve", "norm", "qr", "eigh", "svd", "eig", "lstsq"):
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


def test_matmul():
    import rustlinalg

    A = np.load("/app/fixtures/A_matmul.npy")
    B = np.load("/app/fixtures/B_matmul.npy")
    C = _array64(rustlinalg.matmul(A, B), 2)
    assert C.dtype == np.float64
    np.testing.assert_allclose(C, A @ B, rtol=1e-10)


def test_matmul_identity():
    import rustlinalg

    A = np.load("/app/fixtures/A_matmul.npy")
    I = np.eye(A.shape[0], dtype=np.float64)
    C = rustlinalg.matmul(I, A)
    np.testing.assert_allclose(C, A, rtol=1e-12)


def test_cholesky():
    import rustlinalg

    A = np.load("/app/fixtures/A_spd.npy")
    L = _array64(rustlinalg.cholesky(A), 2)
    assert L.dtype == np.float64
    assert np.allclose(L, np.tril(L))
    np.testing.assert_allclose(L @ L.T, A, rtol=1e-10)


def test_cholesky_identity():
    import rustlinalg

    I = np.eye(5, dtype=np.float64)
    L = rustlinalg.cholesky(I)
    np.testing.assert_allclose(L, I, atol=1e-15)


def test_solve_spd():
    import rustlinalg

    A = np.load("/app/fixtures/A_spd.npy")
    b = np.load("/app/fixtures/b_vec.npy")
    x = _array64(rustlinalg.solve_spd(A, b), 1)
    assert x.dtype == np.float64
    np.testing.assert_allclose(A @ x, b, rtol=1e-10)


def test_norm2():
    import rustlinalg

    b = np.load("/app/fixtures/b_vec.npy")
    result = rustlinalg.norm2(b)
    expected = float(np.linalg.norm(b))
    assert isinstance(result, float)
    np.testing.assert_allclose(result, expected, rtol=1e-12)


def test_norm2_zero():
    import rustlinalg

    z = np.zeros(10, dtype=np.float64)
    assert rustlinalg.norm2(z) == 0.0


def test_qr_tall():
    import rustlinalg

    A = np.load("/app/fixtures/A_qr.npy")
    Q, R = rustlinalg.qr(A)
    Q = _array64(Q, 2)
    R = _array64(R, 2)
    m, n = A.shape
    assert Q.shape == (m, m)
    assert R.shape == (m, n)
    np.testing.assert_allclose(Q.T @ Q, np.eye(m), atol=1e-10)
    np.testing.assert_allclose(Q @ R, A, rtol=1e-10)
    assert np.allclose(R, np.triu(R), atol=1e-12)


def test_qr_square():
    import rustlinalg

    A = np.load("/app/fixtures/A_qr_sq.npy")
    Q, R = rustlinalg.qr(A)
    Q = _array64(Q, 2)
    R = _array64(R, 2)
    n = A.shape[0]
    np.testing.assert_allclose(Q.T @ Q, np.eye(n), atol=1e-10)
    np.testing.assert_allclose(Q @ R, A, rtol=1e-10)


def test_eig_symmetric():
    import rustlinalg

    A = np.load("/app/fixtures/A_spd.npy")
    vals, vecs = rustlinalg.eig_symmetric(A)
    vals = _array64(vals, 1)
    vecs = _array64(vecs, 2)
    assert np.all(vals > 0)
    assert np.all(np.diff(vals) >= -1e-12)
    np.testing.assert_allclose(vecs @ np.diag(vals) @ vecs.T, A, rtol=1e-8)
    np.testing.assert_allclose(vecs.T @ vecs, np.eye(A.shape[0]), atol=1e-8)


def test_eig_symmetric_diagonal():
    import rustlinalg

    D = np.diag([3.0, 1.0, 4.0, 1.5, 2.0]).astype(np.float64)
    vals, vecs = rustlinalg.eig_symmetric(D)
    vals = _array64(vals, 1)
    np.testing.assert_allclose(vals, np.sort([3.0, 1.0, 4.0, 1.5, 2.0]), atol=1e-10)


def test_svd_tall():
    import rustlinalg

    A = np.load("/app/fixtures/A_svd_tall.npy")
    U, S, Vt = rustlinalg.svd(A)
    U = _array64(U, 2)
    S = _array64(S, 1)
    Vt = _array64(Vt, 2)
    m, n = A.shape
    k = min(m, n)
    assert U.shape == (m, m)
    assert Vt.shape == (n, n)
    assert S.shape == (k,)
    assert np.all(S >= -1e-14)
    assert np.all(np.diff(S) <= 1e-12)
    np.testing.assert_allclose(U[:, :k] @ np.diag(S) @ Vt[:k, :], A, rtol=1e-8)


def test_svd_wide():
    import rustlinalg

    A = np.load("/app/fixtures/A_svd_wide.npy")
    U, S, Vt = rustlinalg.svd(A)
    U = _array64(U, 2)
    S = _array64(S, 1)
    Vt = _array64(Vt, 2)
    m, n = A.shape
    k = min(m, n)
    np.testing.assert_allclose(U[:, :k] @ np.diag(S) @ Vt[:k, :], A, rtol=1e-8)


def test_matrix_exp_zero():
    import rustlinalg

    Z = np.zeros((4, 4), dtype=np.float64)
    E = _array64(rustlinalg.matrix_exp(Z), 2)
    np.testing.assert_allclose(E, np.eye(4), atol=1e-14)


def test_matrix_exp_identity():
    import rustlinalg

    I = np.eye(4, dtype=np.float64)
    E = _array64(rustlinalg.matrix_exp(I), 2)
    np.testing.assert_allclose(E, np.exp(1.0) * np.eye(4), rtol=1e-10)


def test_matrix_exp_small():
    import rustlinalg

    A = np.load("/app/fixtures/A_exp_small.npy")
    ref = np.load("/app/fixtures/A_exp_small_ref.npy")
    E = _array64(rustlinalg.matrix_exp(A), 2)
    np.testing.assert_allclose(E, ref, rtol=1e-6)


def test_solve_lstsq():
    import rustlinalg

    A = np.load("/app/fixtures/A_lstsq.npy")
    b = np.load("/app/fixtures/b_lstsq.npy")
    x = _array64(rustlinalg.solve_lstsq(A, b), 1)
    assert x.shape == (A.shape[1],)
    x_ref, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
    np.testing.assert_allclose(x, x_ref, rtol=1e-8)


def test_solve_lstsq_square():
    import rustlinalg

    A = np.load("/app/fixtures/A_lstsq_sq.npy")
    b = np.load("/app/fixtures/b_lstsq_sq.npy")
    x = _array64(rustlinalg.solve_lstsq(A, b), 1)
    x_ref = np.linalg.solve(A, b)
    np.testing.assert_allclose(x, x_ref, rtol=1e-8)
