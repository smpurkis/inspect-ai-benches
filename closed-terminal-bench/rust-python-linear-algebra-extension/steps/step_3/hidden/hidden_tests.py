import numpy as np
import pytest


SCHUR_RECON_TOL = 1e-8
SCHUR_ORTHO_TOL = 1e-8
SCHUR_STRUCT_TOL = 1e-10
CARE_RES_TOL = 1e-7
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


def _noncontiguous_square_view(a: np.ndarray) -> np.ndarray:
    holder = np.zeros((a.shape[0] * 2, a.shape[1] * 2), dtype=np.float64)
    holder[::2, ::2] = a
    return holder[::2, ::2]


def _noncontiguous_rect_view(a: np.ndarray) -> np.ndarray:
    holder = np.zeros((a.shape[0] * 2, a.shape[1] * 2), dtype=np.float64)
    holder[::2, ::2] = a
    return holder[::2, ::2]


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
    assert q.shape == (n, n)
    assert t.shape == (n, n)
    assert q.dtype == np.float64
    assert t.dtype == np.float64

    ortho = np.linalg.norm(q.T @ q - np.eye(n), ord="fro")
    recon = np.linalg.norm(q @ t @ q.T - a, ord="fro")
    lower2 = _max_abs(np.tril(t, k=-2))

    assert ortho < SCHUR_ORTHO_TOL, f"||Q^TQ-I||_F={ortho:.3e}"
    assert recon < SCHUR_RECON_TOL, f"||QTQ^T-A||_F={recon:.3e}"
    assert lower2 < SCHUR_STRUCT_TOL, f"T lower-2 max={lower2:.3e}"

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
            assert disc <= 1e-8, f"2x2 block discriminant={disc:.3e}"
            i += 2
        else:
            i += 1

    assert complex_blocks >= min_complex_blocks, (
        f"expected at least {min_complex_blocks} complex 2x2 block(s), got {complex_blocks}"
    )


def _assert_care_solution(
    a: np.ndarray,
    b: np.ndarray,
    q_mat: np.ndarray,
    r: np.ndarray,
    x: np.ndarray,
) -> None:
    x = _array64(x, 2)
    rinv = np.linalg.inv(r)
    residual = a.T @ x + x @ a - x @ b @ rinv @ b.T @ x + q_mat
    sym_err = np.linalg.norm(x - x.T, ord="fro")
    res_err = np.linalg.norm(residual, ord="fro")
    closed_loop = a - b @ rinv @ b.T @ x
    max_real = float(np.max(np.real(np.linalg.eigvals(closed_loop))))

    assert sym_err < CARE_SYM_TOL, f"symmetry error={sym_err:.3e}"
    assert res_err < CARE_RES_TOL, f"CARE residual={res_err:.3e}"
    assert max_real < -1e-8, f"closed-loop max real part={max_real:.3e}"


def test_hidden_real_schur_multiple_complex_blocks_and_views() -> None:
    import rustlinalg

    t_ref = np.array(
        [
            [0.4, 1.7, 0.2, -0.3, 0.1, 0.0],
            [-1.7, 0.4, 0.5, 0.1, 0.0, -0.2],
            [0.0, 0.0, -0.8, 2.1, 0.4, 0.3],
            [0.0, 0.0, -2.1, -0.8, -0.2, 0.1],
            [0.0, 0.0, 0.0, 0.0, 1.6, -0.7],
            [0.0, 0.0, 0.0, 0.0, 0.0, -2.3],
        ],
        dtype=np.float64,
    )
    q_ref = _random_orthogonal(401, 6)
    a = q_ref @ t_ref @ q_ref.T
    a_view = _noncontiguous_square_view(a)
    q, t = rustlinalg.real_schur(a_view)
    _assert_real_schur(a, q, t, min_complex_blocks=2)


def test_hidden_real_schur_nonnormal_family() -> None:
    import rustlinalg

    upper = np.array(
        [
            [1.2, 3.5, -4.0, 2.0, 0.5, -1.0, 0.7],
            [0.0, -0.4, 1.3, -0.8, 0.0, 0.3, -0.6],
            [0.0, 0.0, 0.6, 1.8, -2.0, 0.4, 0.2],
            [0.0, 0.0, -1.8, 0.6, 1.1, -0.5, 0.9],
            [0.0, 0.0, 0.0, 0.0, -2.5, 4.2, -1.7],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.3, 2.4],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.1],
        ],
        dtype=np.float64,
    )
    q_ref = _random_orthogonal(403, 7)
    a = q_ref @ upper @ q_ref.T
    q, t = rustlinalg.real_schur(a)
    _assert_real_schur(a, q, t, min_complex_blocks=1)


def test_hidden_solve_care_varied_systems() -> None:
    import rustlinalg

    cases = [
        (
            np.array(
                [
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                    [1.0, -5.0, -2.0],
                ],
                dtype=np.float64,
            ),
            np.array([[0.0], [0.0], [1.0]], dtype=np.float64),
            np.diag([10.0, 2.0, 1.0]).astype(np.float64),
            np.array([[0.8]], dtype=np.float64),
        ),
        (
            np.array(
                [
                    [1.2, 0.3, 0.0, 0.0],
                    [0.0, 0.8, 1.0, 0.0],
                    [0.0, 0.0, -0.4, 1.0],
                    [0.2, 0.0, -1.5, -0.2],
                ],
                dtype=np.float64,
            ),
            np.array(
                [
                    [1.0, 0.0],
                    [0.0, 1.0],
                    [1.0, 0.0],
                    [0.0, 1.0],
                ],
                dtype=np.float64,
            ),
            np.array(
                [
                    [6.0, 1.0, 0.0, 0.0],
                    [1.0, 4.0, 0.5, 0.0],
                    [0.0, 0.5, 5.0, 1.0],
                    [0.0, 0.0, 1.0, 3.0],
                ],
                dtype=np.float64,
            ),
            np.array([[2.0, 0.3], [0.3, 1.5]], dtype=np.float64),
        ),
    ]

    for idx, (a, b, q_mat, r) in enumerate(cases):
        if idx == 1:
            a = _noncontiguous_square_view(a)
            q_mat = _noncontiguous_square_view(q_mat)
            b = _noncontiguous_rect_view(b)
            r = _noncontiguous_square_view(r)
        x = rustlinalg.solve_care(a, b, q_mat, r)
        _assert_care_solution(
            np.asarray(a), np.asarray(b), np.asarray(q_mat), np.asarray(r), x
        )


def test_hidden_step3_invalid_inputs_raise_value_error() -> None:
    import rustlinalg

    with pytest.raises(ValueError):
        rustlinalg.real_schur(np.array(3.14, dtype=np.float64))

    with pytest.raises(ValueError):
        rustlinalg.real_schur(np.array([[1.0 + 2.0j]], dtype=np.complex128))

    a = np.array([[0.0, 1.0], [2.0, -3.0]], dtype=np.float64)
    b = np.array([[0.0], [1.0]], dtype=np.float64)
    q_mat = np.eye(2, dtype=np.float64)

    with pytest.raises(ValueError):
        rustlinalg.solve_care(
            a, b, q_mat, np.array([[1.0, 2.0], [2.0, 4.0]], dtype=np.float64)
        )

    with pytest.raises(ValueError):
        rustlinalg.solve_care(
            a,
            b,
            np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64),
            np.array([[1.0]], dtype=np.float64),
        )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
