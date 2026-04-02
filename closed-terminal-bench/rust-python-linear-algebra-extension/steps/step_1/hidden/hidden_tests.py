import importlib.util
import re
from pathlib import Path

import numpy as np
import pytest


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


def test_hidden_pipeline_stricter_thresholds():
    module = _load_pipeline_module()
    cases = module.run_pipeline("rustlinalg")

    for item in cases:
        assert item["matmul_max_abs"] < 5e-9
        assert item["cholesky_recon_max_abs"] < 5e-9
        assert item["solve_spd_max_abs"] < 5e-9
        assert item["norm2_abs"] < 1e-10
        assert item["qr_recon_max_abs"] < 5e-8
        assert item["eig_vals_max_abs"] < 5e-8
        assert item["svd_recon_max_abs"] < 8e-7
        assert item["matrix_exp_max_abs"] < 8e-3
        assert item["lstsq_max_abs"] < 8e-8


# ── Merged from old step 2: edge cases and stress tests ──────────────


def test_hidden_matmul_stress_and_shape_errors():
    import rustlinalg

    rng = np.random.default_rng(7)
    for m, k, n in [(8, 9, 7), (16, 11, 13), (25, 20, 14)]:
        a = rng.standard_normal((m, k)).astype(np.float64)
        b = rng.standard_normal((k, n)).astype(np.float64)
        out = rustlinalg.matmul(a, b)
        np.testing.assert_allclose(out, a @ b, rtol=1e-8, atol=1e-9)

    bad = rng.standard_normal((5, 4)).astype(np.float64)
    with pytest.raises(Exception):
        rustlinalg.matmul(bad, rng.standard_normal((3, 6)).astype(np.float64))


def test_hidden_cholesky_and_solve_edge_cases():
    import rustlinalg

    rng = np.random.default_rng(42)
    x = rng.standard_normal((14, 14))
    a = (x @ x.T + 1e-2 * np.eye(14)).astype(np.float64)
    b = rng.standard_normal(14).astype(np.float64)

    l = _array64(rustlinalg.cholesky(a), 2)
    assert np.allclose(l, np.tril(l), atol=1e-10)
    np.testing.assert_allclose(l @ l.T, a, rtol=1e-8, atol=1e-9)

    sol = _array64(rustlinalg.solve_spd(a, b), 1)
    np.testing.assert_allclose(a @ sol, b, rtol=1e-8, atol=1e-8)

    not_spd = np.array([[1.0, 2.0], [2.0, 1.0]], dtype=np.float64)
    with pytest.raises(Exception):
        rustlinalg.cholesky(not_spd)
    with pytest.raises(Exception):
        rustlinalg.solve_spd(not_spd, np.array([1.0, 2.0], dtype=np.float64))


def test_hidden_performance_sensitive_repeatability():
    import rustlinalg

    rng = np.random.default_rng(123)
    a = rng.standard_normal((48, 48)).astype(np.float64)
    b = rng.standard_normal((48, 48)).astype(np.float64)

    baseline = rustlinalg.matmul(a, b)
    for _ in range(12):
        out = rustlinalg.matmul(a, b)
        np.testing.assert_allclose(out, baseline, rtol=1e-10, atol=1e-12)


def test_hidden_error_handling_shapes():
    import rustlinalg

    with pytest.raises(Exception):
        rustlinalg.norm2(np.zeros((3, 3), dtype=np.float64))

    with pytest.raises(Exception):
        rustlinalg.solve_lstsq(
            np.zeros((5, 3), dtype=np.float64),
            np.zeros((5, 1), dtype=np.float64),
        )

    with pytest.raises(Exception):
        rustlinalg.qr(np.zeros((4,), dtype=np.float64))

    with pytest.raises(Exception):
        rustlinalg.eig_symmetric(np.zeros((3, 4), dtype=np.float64))

    with pytest.raises(Exception):
        rustlinalg.matrix_exp(np.zeros((2, 3), dtype=np.float64))

    with pytest.raises(Exception):
        rustlinalg.solve_spd(
            np.eye(5, dtype=np.float64),
            np.zeros(4, dtype=np.float64),
        )


def test_hidden_edge_and_parity_cases():
    import rustlinalg

    rng = np.random.default_rng(2026)

    # SPD near-conditioning stress
    q, _ = np.linalg.qr(rng.standard_normal((10, 10)))
    d = np.diag(np.geomspace(1e-2, 4.0, 10))
    a = (q @ d @ q.T).astype(np.float64)
    b = rng.standard_normal(10).astype(np.float64)

    x = _array64(rustlinalg.solve_spd(a, b), 1)
    np.testing.assert_allclose(a @ x, b, rtol=2e-6, atol=2e-7)

    # Symmetric eig parity
    s = rng.standard_normal((9, 9))
    s = (s + s.T) * 0.5
    vals, vecs = rustlinalg.eig_symmetric(s)
    vals = _array64(vals, 1)
    vecs = _array64(vecs, 2)
    vals_ref, _ = np.linalg.eigh(s)
    np.testing.assert_allclose(vals, vals_ref, rtol=2e-6, atol=3e-7)
    np.testing.assert_allclose(vecs @ np.diag(vals) @ vecs.T, s, rtol=2e-6, atol=5e-7)

    # SVD stress
    m = rng.standard_normal((17, 11)).astype(np.float64)
    u, sig, vt = rustlinalg.svd(m)
    u = _array64(u, 2)
    sig = _array64(sig, 1)
    vt = _array64(vt, 2)
    k = min(m.shape)
    np.testing.assert_allclose(
        u[:, :k] @ np.diag(sig) @ vt[:k, :], m, rtol=2e-6, atol=2e-7
    )

    # matrix exp parity on small norm
    a_exp = rng.standard_normal((5, 5)).astype(np.float64) * 0.03
    vals_e, vecs_e = np.linalg.eig(a_exp)
    exp_ref = np.real_if_close(vecs_e @ np.diag(np.exp(vals_e)) @ np.linalg.inv(vecs_e))
    exp_out = _array64(rustlinalg.matrix_exp(a_exp), 2)
    np.testing.assert_allclose(exp_out, exp_ref, rtol=2.5e-2, atol=6e-3)


def test_hidden_errors_must_raise():
    import rustlinalg

    with pytest.raises(Exception):
        rustlinalg.qr(np.zeros((4,), dtype=np.float64))

    with pytest.raises(Exception):
        rustlinalg.eig_symmetric(np.zeros((3, 4), dtype=np.float64))

    with pytest.raises(Exception):
        rustlinalg.matrix_exp(np.zeros((2, 3), dtype=np.float64))

    with pytest.raises(Exception):
        rustlinalg.solve_spd(
            np.eye(5, dtype=np.float64),
            np.zeros(4, dtype=np.float64),
        )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
