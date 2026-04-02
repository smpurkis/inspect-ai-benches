import numpy as np
import pytest


def _array64(value, ndim: int | None = None) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    if ndim is not None:
        assert arr.ndim == ndim, f"expected {ndim}D output, got shape {arr.shape}"
    return arr


def test_hidden_lu_stress():
    import rustlinalg

    rng = np.random.default_rng(3001)

    # Larger matrix
    for n in [20, 32]:
        a = rng.standard_normal((n, n)).astype(np.float64)
        a += np.eye(n) * 1.5

        l, u, piv = rustlinalg.lu_factor(a)
        l = _array64(l, 2)
        u = _array64(u, 2)

        assert l.shape == (n, n)
        assert u.shape == (n, n)
        assert len(piv) == n

        assert np.allclose(l, np.tril(l), atol=1e-12)
        np.testing.assert_allclose(np.diag(l), np.ones(n), atol=1e-12)
        assert np.allclose(u, np.triu(u), atol=1e-12)

        perm = np.eye(n)
        for i, p in enumerate(piv):
            perm[[i, p]] = perm[[p, i]]
        np.testing.assert_allclose(perm @ a, l @ u, rtol=1e-8, atol=1e-9)


def test_hidden_solve_stress():
    import rustlinalg

    rng = np.random.default_rng(3002)

    # Ill-conditioned but non-singular
    q, _ = np.linalg.qr(rng.standard_normal((12, 12)))
    d = np.diag(np.geomspace(1e-3, 5.0, 12))
    a = (q @ d @ q.T).astype(np.float64)
    b = rng.standard_normal(12).astype(np.float64)

    x = _array64(rustlinalg.solve(a, b), 1)
    np.testing.assert_allclose(a @ x, b, rtol=1e-6, atol=1e-7)

    # Verify against numpy
    x_ref = np.linalg.solve(a, b)
    np.testing.assert_allclose(x, x_ref, rtol=1e-6, atol=1e-7)


def test_hidden_det_stress():
    import rustlinalg

    rng = np.random.default_rng(3003)

    for n in [4, 8, 16]:
        a = rng.standard_normal((n, n)).astype(np.float64)
        a += np.eye(n)

        d = rustlinalg.det(a)
        d_ref = float(np.linalg.det(a))
        np.testing.assert_allclose(d, d_ref, rtol=1e-6, atol=1e-8)

    # Negative determinant
    a = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float64)
    d = rustlinalg.det(a)
    np.testing.assert_allclose(d, -1.0, atol=1e-12)

    # Near-singular (det close to 0 but not 0)
    a = np.eye(5, dtype=np.float64)
    a[0, 0] = 1e-8
    d = rustlinalg.det(a)
    np.testing.assert_allclose(d, 1e-8, rtol=1e-4)


def test_hidden_solve_non_contiguous_input():
    """Verify solve handles non-contiguous numpy views correctly."""
    import rustlinalg

    rng = np.random.default_rng(3004)
    big = rng.standard_normal((20, 20)).astype(np.float64)
    big += np.eye(20) * 3.0

    # Take a non-contiguous slice
    a = big[::2, ::2]  # 10x10 non-contiguous
    assert not a.flags["C_CONTIGUOUS"]

    b_big = rng.standard_normal(20).astype(np.float64)
    b = b_big[::2]  # non-contiguous vector

    x = _array64(rustlinalg.solve(a, b), 1)
    np.testing.assert_allclose(np.ascontiguousarray(a) @ x, np.ascontiguousarray(b), rtol=1e-8, atol=1e-9)


def test_hidden_lu_non_contiguous_input():
    """Verify lu_factor handles non-contiguous numpy views correctly."""
    import rustlinalg

    rng = np.random.default_rng(3005)
    big = rng.standard_normal((16, 16)).astype(np.float64)
    big += np.eye(16) * 2.0

    a = big[::2, ::2]  # 8x8 non-contiguous
    assert not a.flags["C_CONTIGUOUS"]

    l, u, piv = rustlinalg.lu_factor(a)
    l = _array64(l, 2)
    u = _array64(u, 2)
    n = a.shape[0]

    perm = np.eye(n)
    for i, p in enumerate(piv):
        perm[[i, p]] = perm[[p, i]]
    np.testing.assert_allclose(perm @ np.ascontiguousarray(a), l @ u, rtol=1e-8, atol=1e-9)


def test_hidden_lu_solve_det_consistency():
    """Cross-validate lu_factor, solve, and det against each other."""
    import rustlinalg

    rng = np.random.default_rng(99)

    for n in [4, 8, 12]:
        a = rng.standard_normal((n, n)).astype(np.float64)
        a += np.eye(n) * 2.0

        # 1. det(A) should equal product of diag(U) adjusted for pivot sign
        l, u, piv = rustlinalg.lu_factor(a)
        u = _array64(u, 2)
        det_from_lu = float(np.prod(np.diag(u)))
        # Count row swaps to determine sign
        swaps = sum(1 for i, p in enumerate(piv) if i != p)
        det_from_lu *= (-1) ** swaps
        det_direct = rustlinalg.det(a)
        np.testing.assert_allclose(det_direct, det_from_lu, rtol=1e-6, atol=1e-10)

        # 2. solve(A, b) result must satisfy A @ x == b
        b = rng.standard_normal(n).astype(np.float64)
        x = _array64(rustlinalg.solve(a, b), 1)
        np.testing.assert_allclose(a @ x, b, rtol=1e-8, atol=1e-9)

        # 3. det(A) should match numpy reference
        det_ref = float(np.linalg.det(a))
        np.testing.assert_allclose(det_direct, det_ref, rtol=1e-6, atol=1e-10)


def test_hidden_errors_must_raise_valueerror():
    import rustlinalg

    # 3D tensor
    with pytest.raises(Exception):
        rustlinalg.lu_factor(np.zeros((2, 2, 2), dtype=np.float64))

    with pytest.raises(Exception):
        rustlinalg.det(np.zeros((2, 2, 2), dtype=np.float64))

    # Object dtype
    with pytest.raises(Exception):
        rustlinalg.solve(
            np.array([["a", "b"], ["c", "d"]], dtype=object),
            np.array([1.0, 2.0], dtype=np.float64),
        )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
