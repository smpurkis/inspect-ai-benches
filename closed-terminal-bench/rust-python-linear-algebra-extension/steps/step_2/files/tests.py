import numpy as np
import pytest


def _array64(value, ndim: int | None = None) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    if ndim is not None:
        assert arr.ndim == ndim, f"expected {ndim}D output, got shape {arr.shape}"
    return arr


def test_solve_singular_matrix_raises():
    """solve() must raise an exception for a singular matrix."""
    import rustlinalg

    singular = np.array([[1.0, 2.0], [2.0, 4.0]], dtype=np.float64)  # row 2 = 2 * row 1
    b = np.array([1.0, 2.0], dtype=np.float64)
    with pytest.raises(Exception):
        rustlinalg.solve(singular, b)

    # Also test a matrix with a zero row
    zero_row = np.array([[1.0, 0.0], [0.0, 0.0]], dtype=np.float64)
    with pytest.raises(Exception):
        rustlinalg.solve(zero_row, b)


def test_lu_factor_identity_matrix():
    """lu_factor(I) should return L=I, U=I, piv=[0,1,...,n-1]."""
    import rustlinalg

    for n in [2, 5, 8]:
        eye = np.eye(n, dtype=np.float64)
        l, u, piv = rustlinalg.lu_factor(eye)
        l = _array64(l, 2)
        u = _array64(u, 2)

        np.testing.assert_allclose(l, np.eye(n), atol=1e-12)
        np.testing.assert_allclose(u, np.eye(n), atol=1e-12)
        assert list(piv) == list(range(n)), (
            f"pivot for identity should be [0..{n-1}], got {list(piv)}"
        )


def test_import_step2_functions():
    import rustlinalg

    for name in ("lu_factor", "solve", "det"):
        assert hasattr(rustlinalg, name), f"Missing function: {name}"
        assert callable(getattr(rustlinalg, name)), f"{name} is not callable"


def test_runtime_does_not_delegate_to_python_linalg(monkeypatch):
    import rustlinalg

    def _blocked(*args, **kwargs):
        raise AssertionError(
            "rustlinalg must not delegate numerical work to Python numpy/scipy"
        )

    for name in ("solve", "det", "inv"):
        monkeypatch.setattr(np.linalg, name, _blocked)

    try:
        import scipy.linalg as scipy_linalg
    except Exception:
        scipy_linalg = None
    if scipy_linalg is not None:
        for name in ("solve", "det", "inv", "lu", "lu_factor"):
            monkeypatch.setattr(scipy_linalg, name, _blocked, raising=False)

    rng = np.random.default_rng(500)
    a = rng.standard_normal((5, 5)).astype(np.float64)
    a += np.eye(5) * 3.0  # ensure non-singular
    b = rng.standard_normal(5).astype(np.float64)

    l, u, piv = rustlinalg.lu_factor(a)
    assert _array64(l, 2).shape == (5, 5)
    assert _array64(u, 2).shape == (5, 5)

    x = _array64(rustlinalg.solve(a, b), 1)
    assert x.shape == (5,)

    d = rustlinalg.det(a)
    assert isinstance(d, float)


def test_lu_factor_basic():
    import rustlinalg

    rng = np.random.default_rng(201)
    for n in [3, 6, 10]:
        a = rng.standard_normal((n, n)).astype(np.float64)
        a += np.eye(n) * 2.0

        l, u, piv = rustlinalg.lu_factor(a)
        l = _array64(l, 2)
        u = _array64(u, 2)

        assert l.shape == (n, n), f"L shape mismatch: {l.shape}"
        assert u.shape == (n, n), f"U shape mismatch: {u.shape}"
        assert len(piv) == n, f"pivot length mismatch: {len(piv)}"

        # L must be lower-triangular with unit diagonal
        assert np.allclose(l, np.tril(l), atol=1e-12), "L is not lower-triangular"
        np.testing.assert_allclose(np.diag(l), np.ones(n), atol=1e-12)

        # U must be upper-triangular
        assert np.allclose(u, np.triu(u), atol=1e-12), "U is not upper-triangular"

        # Reconstruct P @ A and verify P @ A == L @ U
        perm = np.eye(n)
        for i, p in enumerate(piv):
            perm[[i, p]] = perm[[p, i]]
        np.testing.assert_allclose(perm @ a, l @ u, rtol=1e-8, atol=1e-9)


def test_solve_basic():
    import rustlinalg

    rng = np.random.default_rng(202)
    for n in [3, 8, 15]:
        a = rng.standard_normal((n, n)).astype(np.float64)
        a += np.eye(n) * 3.0
        b = rng.standard_normal(n).astype(np.float64)

        x = _array64(rustlinalg.solve(a, b), 1)
        assert x.shape == (n,)
        np.testing.assert_allclose(a @ x, b, rtol=1e-8, atol=1e-9)

        # Compare with numpy
        x_ref = np.linalg.solve(a, b)
        np.testing.assert_allclose(x, x_ref, rtol=1e-8, atol=1e-9)


def test_det_basic():
    import rustlinalg

    rng = np.random.default_rng(203)
    for n in [2, 5, 10]:
        a = rng.standard_normal((n, n)).astype(np.float64)
        a += np.eye(n) * 2.0

        d = rustlinalg.det(a)
        d_ref = float(np.linalg.det(a))
        assert isinstance(d, float)
        np.testing.assert_allclose(d, d_ref, rtol=1e-8, atol=1e-10)

    # Identity determinant is 1
    eye = np.eye(4, dtype=np.float64)
    np.testing.assert_allclose(rustlinalg.det(eye), 1.0, atol=1e-12)


def test_error_handling():
    import rustlinalg

    # Non-square
    with pytest.raises(Exception):
        rustlinalg.lu_factor(np.zeros((3, 4), dtype=np.float64))

    with pytest.raises(Exception):
        rustlinalg.solve(
            np.zeros((3, 4), dtype=np.float64),
            np.zeros(3, dtype=np.float64),
        )

    with pytest.raises(Exception):
        rustlinalg.det(np.zeros((3, 4), dtype=np.float64))

    # 1D input
    with pytest.raises(Exception):
        rustlinalg.lu_factor(np.zeros(5, dtype=np.float64))

    # Mismatched b vector
    with pytest.raises(Exception):
        rustlinalg.solve(
            np.eye(3, dtype=np.float64),
            np.zeros(5, dtype=np.float64),
        )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
