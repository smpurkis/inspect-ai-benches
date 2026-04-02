import numpy as np
import pytest


SCHUR_RECON_TOL = 1e-8
SCHUR_ORTHO_TOL = 1e-8
SCHUR_STRUCT_TOL = 1e-10
CARE_RES_TOL = 5e-8
CARE_SYM_TOL = 1e-10


def _array64(value, ndim: int | None = None) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    if ndim is not None:
        assert arr.ndim == ndim, f"expected {ndim}D output, got shape {arr.shape}"
    return arr


def _max_abs(arr: np.ndarray) -> float:
    return float(np.max(np.abs(arr))) if arr.size else 0.0


def _random_orthogonal(seed: int, n: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    q, r = np.linalg.qr(rng.standard_normal((n, n)))
    signs = np.where(np.diag(r) >= 0.0, 1.0, -1.0)
    return q * signs


def test_real_schur_symmetric_produces_diagonal():
    """Schur decomposition of a symmetric matrix should produce a diagonal T (eigenvalues on diagonal)."""
    import rustlinalg

    rng = np.random.default_rng(401)
    s = rng.standard_normal((6, 6)).astype(np.float64)
    s = 0.5 * (s + s.T)  # symmetric

    q, t = rustlinalg.real_schur(s)
    t = _array64(t, 2)
    q = _array64(q, 2)

    # T should be diagonal for symmetric input (no 2x2 blocks)
    off_diag = t - np.diag(np.diag(t))
    assert _max_abs(off_diag) < 1e-8, (
        f"Schur T of symmetric matrix should be diagonal, "
        f"max off-diagonal = {_max_abs(off_diag):.3e}"
    )

    # Eigenvalues on diagonal of T should match numpy eigh
    schur_eigs = np.sort(np.diag(t))
    ref_eigs = np.sort(np.linalg.eigvalsh(s))
    np.testing.assert_allclose(schur_eigs, ref_eigs, rtol=1e-8, atol=1e-10)


def test_solve_care_diagonal_system():
    """CARE with A=diag, B=I, Q=diag, R=I has a known closed-form solution."""
    import rustlinalg

    # For A=diag(a_i), B=I, Q=diag(q_i), R=I, the CARE solution X is diagonal
    # with x_i = -a_i + sqrt(a_i^2 + q_i)
    n = 3
    a_diag = np.array([-1.0, -2.0, -0.5])
    q_diag = np.array([4.0, 1.0, 9.0])

    a = np.diag(a_diag).astype(np.float64)
    b = np.eye(n, dtype=np.float64)
    q_mat = np.diag(q_diag).astype(np.float64)
    r = np.eye(n, dtype=np.float64)

    x = rustlinalg.solve_care(a, b, q_mat, r)
    x = _array64(x, 2)

    # Verify via analytic solution: x_i = -a_i + sqrt(a_i^2 + q_i)
    x_analytic = np.diag(-a_diag + np.sqrt(a_diag**2 + q_diag))
    np.testing.assert_allclose(x, x_analytic, rtol=1e-6, atol=1e-8)

    # Also verify it satisfies the CARE equation
    _assert_care_solution(a, b, q_mat, r, x)


def test_runtime_does_not_delegate_to_python_linalg(monkeypatch):
    import rustlinalg

    def _blocked(*args, **kwargs):
        raise AssertionError(
            "rustlinalg must not delegate numerical work to Python numpy/scipy"
        )

    for name in ("eig", "eigvals", "solve", "inv"):
        monkeypatch.setattr(np.linalg, name, _blocked)

    try:
        import scipy.linalg as scipy_linalg
    except Exception:
        scipy_linalg = None

    if scipy_linalg is not None:
        for name in (
            "schur",
            "rsf2csf",
            "solve_continuous_are",
            "eig",
            "eigvals",
            "solve",
            "inv",
            "hessenberg",
        ):
            monkeypatch.setattr(scipy_linalg, name, _blocked, raising=False)

    a_schur = np.array(
        [
            [0.3, 2.0, -1.0],
            [-2.5, 0.1, 0.5],
            [0.2, -0.4, 1.7],
        ],
        dtype=np.float64,
    )
    q, t = rustlinalg.real_schur(a_schur)
    assert _array64(q, 2).shape == a_schur.shape
    assert _array64(t, 2).shape == a_schur.shape

    a = np.array([[0.0, 1.0], [2.0, -3.0]], dtype=np.float64)
    b = np.array([[0.0], [1.0]], dtype=np.float64)
    q_mat = np.diag([4.0, 1.0]).astype(np.float64)
    r = np.array([[2.0]], dtype=np.float64)
    x = rustlinalg.solve_care(a, b, q_mat, r)
    assert _array64(x, 2).shape == a.shape


def _assert_real_schur(
    a: np.ndarray,
    q: np.ndarray,
    t: np.ndarray,
    *,
    min_complex_blocks: int = 0,
) -> None:
    q = _array64(q, 2)
    t = _array64(t, 2)
    n = a.shape[0]
    assert q.dtype == np.float64
    assert t.dtype == np.float64
    assert q.shape == (n, n), f"Q must have shape {(n, n)}, got {q.shape}"
    assert t.shape == (n, n), f"T must have shape {(n, n)}, got {t.shape}"

    ortho = np.linalg.norm(q.T @ q - np.eye(n), ord="fro")
    recon = np.linalg.norm(q @ t @ q.T - a, ord="fro")
    lower2 = _max_abs(np.tril(t, k=-2))

    assert ortho < SCHUR_ORTHO_TOL, (
        f"||Q^TQ-I||_F={ortho:.3e} exceeds {SCHUR_ORTHO_TOL}"
    )
    assert recon < SCHUR_RECON_TOL, (
        f"||QTQ^T-A||_F={recon:.3e} exceeds {SCHUR_RECON_TOL}"
    )
    assert lower2 < SCHUR_STRUCT_TOL, (
        f"entries below first subdiagonal max={lower2:.3e} exceeds {SCHUR_STRUCT_TOL}"
    )

    complex_blocks = 0
    i = 0
    while i < n - 1:
        if abs(t[i + 1, i]) > SCHUR_STRUCT_TOL:
            complex_blocks += 1
            if i > 0:
                assert abs(t[i, i - 1]) <= SCHUR_STRUCT_TOL
            if i + 2 < n:
                assert abs(t[i + 2, i + 1]) <= SCHUR_STRUCT_TOL

            block = t[i : i + 2, i : i + 2]
            disc = (block[0, 0] - block[1, 1]) ** 2 + 4.0 * block[0, 1] * block[1, 0]
            assert disc <= 1e-8, (
                "nontrivial 2x2 Schur blocks must represent a complex-conjugate pair; "
                f"discriminant={disc:.3e}"
            )
            i += 2
        else:
            i += 1

    assert complex_blocks >= min_complex_blocks, (
        f"expected at least {min_complex_blocks} complex 2x2 Schur block(s), got {complex_blocks}"
    )


def _assert_care_solution(
    a: np.ndarray,
    b: np.ndarray,
    q_mat: np.ndarray,
    r: np.ndarray,
    x: np.ndarray,
) -> None:
    x = _array64(x, 2)
    n = a.shape[0]
    assert x.dtype == np.float64
    assert x.shape == (n, n), f"X must have shape {(n, n)}, got {x.shape}"

    rinv = np.linalg.inv(r)
    residual = a.T @ x + x @ a - x @ b @ rinv @ b.T @ x + q_mat
    sym_err = np.linalg.norm(x - x.T, ord="fro")
    res_err = np.linalg.norm(residual, ord="fro")
    closed_loop = a - b @ rinv @ b.T @ x
    max_real = float(np.max(np.real(np.linalg.eigvals(closed_loop))))

    assert sym_err < CARE_SYM_TOL, (
        f"symmetry error={sym_err:.3e} exceeds {CARE_SYM_TOL}"
    )
    assert res_err < CARE_RES_TOL, f"CARE residual={res_err:.3e} exceeds {CARE_RES_TOL}"
    assert max_real < -1e-8, f"closed-loop is not stable; max real part={max_real:.3e}"


def test_import_step3_functions() -> None:
    import rustlinalg

    for name in ("real_schur", "solve_care"):
        assert hasattr(rustlinalg, name), f"Missing function: {name}"
        assert callable(getattr(rustlinalg, name)), f"{name} is not callable"


def test_real_schur_general_real_matrix() -> None:
    import rustlinalg

    rng = np.random.default_rng(301)
    a = rng.standard_normal((6, 6)).astype(np.float64)
    q, t = rustlinalg.real_schur(a)
    _assert_real_schur(a, q, t)


def test_real_schur_exposes_complex_pair_block() -> None:
    import rustlinalg

    t_ref = np.array(
        [
            [0.25, 2.0, -0.3, 0.2, 0.1],
            [-2.0, 0.25, 0.4, -0.1, 0.0],
            [0.0, 0.0, -1.7, 0.6, -0.2],
            [0.0, 0.0, 0.0, 3.1, 1.5],
            [0.0, 0.0, 0.0, -1.5, 3.1],
        ],
        dtype=np.float64,
    )
    q_ref = _random_orthogonal(302, 5)
    a = q_ref @ t_ref @ q_ref.T
    q, t = rustlinalg.real_schur(a)
    _assert_real_schur(a, q, t, min_complex_blocks=2)


def test_real_schur_invalid_dimensions_and_types_raise_value_error() -> None:
    import rustlinalg

    with pytest.raises(ValueError):
        rustlinalg.real_schur(np.array([1.0, 2.0, 3.0], dtype=np.float64))

    with pytest.raises(ValueError):
        rustlinalg.real_schur(np.zeros((2, 3), dtype=np.float64))

    with pytest.raises(ValueError):
        rustlinalg.real_schur(np.zeros((2, 2, 2), dtype=np.float64))

    with pytest.raises(ValueError):
        rustlinalg.real_schur(np.array([["x", "y"], ["z", "w"]], dtype=object))


def test_solve_care_small_reference_problem() -> None:
    import rustlinalg

    a = np.array([[0.0, 1.0], [2.0, -3.0]], dtype=np.float64)
    b = np.array([[0.0], [1.0]], dtype=np.float64)
    q_mat = np.array([[4.0, 0.0], [0.0, 1.5]], dtype=np.float64)
    r = np.array([[2.0]], dtype=np.float64)
    x = rustlinalg.solve_care(a, b, q_mat, r)
    _assert_care_solution(a, b, q_mat, r, x)


def test_solve_care_coupled_reference_problem() -> None:
    import rustlinalg

    a = np.array(
        [
            [0.0, 1.0, 0.0, 0.0],
            [-2.0, -0.4, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
            [1.0, 0.0, -2.0, -0.4],
        ],
        dtype=np.float64,
    )
    b = np.array(
        [
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 0.0],
            [0.0, 1.0],
        ],
        dtype=np.float64,
    )
    q_mat = np.array(
        [
            [8.0, 0.3, 0.0, 0.0],
            [0.3, 2.0, 0.2, 0.0],
            [0.0, 0.2, 8.0, 0.3],
            [0.0, 0.0, 0.3, 2.0],
        ],
        dtype=np.float64,
    )
    r = np.array([[2.0, 0.2], [0.2, 1.5]], dtype=np.float64)
    x = rustlinalg.solve_care(a, b, q_mat, r)
    _assert_care_solution(a, b, q_mat, r, x)


def test_solve_care_invalid_dimensions_and_types_raise_value_error() -> None:
    import rustlinalg

    a = np.array([[0.0, 1.0], [2.0, -3.0]], dtype=np.float64)
    b = np.array([[0.0], [1.0]], dtype=np.float64)
    q_mat = np.eye(2, dtype=np.float64)
    r = np.array([[1.0]], dtype=np.float64)

    with pytest.raises(ValueError):
        rustlinalg.solve_care(np.array([1.0, 2.0], dtype=np.float64), b, q_mat, r)

    with pytest.raises(ValueError):
        rustlinalg.solve_care(a, np.zeros((3, 1), dtype=np.float64), q_mat, r)

    with pytest.raises(ValueError):
        rustlinalg.solve_care(
            a, b, np.array([[1.0, 2.0], [0.0, 1.0]], dtype=np.float64), r
        )

    with pytest.raises(ValueError):
        rustlinalg.solve_care(a, b, q_mat, np.array([["bad"]], dtype=object))


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
