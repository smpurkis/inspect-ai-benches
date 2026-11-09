import importlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

FILES = Path("/app/files")
APP = Path("/app")


@pytest.fixture(scope="session")
def module():
    shutil.rmtree(APP / "src", ignore_errors=True)
    shutil.copytree(FILES / "src", APP / "src")
    shutil.copyfile(FILES / "Cargo.toml", APP / "Cargo.toml")
    shutil.copyfile(FILES / "pyproject.toml", APP / "pyproject.toml")
    result = subprocess.run(["maturin", "develop", "--release", "--offline"],
                            cwd=APP, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr[-4000:]
    sys.modules.pop("rustlinalg", None)
    return importlib.import_module("rustlinalg.rustlinalg")


def _assert_schur(mod, a, atol):
    t, q = map(lambda x: np.asarray(x, dtype=np.float64), mod.schur(a))
    n = len(a)
    assert np.all(np.isfinite(t)) and np.all(np.isfinite(q))
    np.testing.assert_allclose(q.T @ q, np.eye(n), atol=atol)
    np.testing.assert_allclose(q @ t @ q.T, a, atol=atol * max(1., np.linalg.norm(a, np.inf)))
    assert np.max(np.abs(np.tril(t, -2)), initial=0.) <= atol * max(1., np.linalg.norm(a, np.inf))
    for i in range(1, n - 1):
        assert not (abs(t[i, i - 1]) > atol and abs(t[i + 1, i]) > atol), "overlapping 2x2 blocks"
    return t


@pytest.mark.parametrize("n,seed", [(3, 811), (5, 812), (9, 813), (16, 814), (24, 815)])
def test_generated_dense_hessenberg_cases(module, n, seed):
    rng = np.random.default_rng(seed)
    a = rng.standard_normal((n, n)).astype(np.float64)
    t = _assert_schur(module, a, 2e-8)
    np.testing.assert_allclose(np.sort_complex(np.linalg.eigvals(t)),
                               np.sort_complex(np.linalg.eigvals(a)), atol=2e-7)


def test_metamorphic_orthogonal_similarity_and_scaling(module):
    rng = np.random.default_rng(90217)
    for n in (4, 7, 12):
        base = rng.standard_normal((n, n))
        u, _ = np.linalg.qr(rng.standard_normal((n, n)))
        transformed = u.T @ base @ u
        expected = np.sort_complex(np.linalg.eigvals(base))
        for scale in (1e-120, 1e-20, 1., 1e20, 1e120):
            t = _assert_schur(module, (scale * transformed).astype(np.float64), 8e-8)
            observed = np.sort_complex(np.linalg.eigvals(t) / scale)
            np.testing.assert_allclose(observed, expected, atol=2e-6)


def test_adversarial_deflation_boundaries(module):
    for scale in (1e-120, 1., 1e120):
        coupled = scale * np.array([[0., 1., 0., 0.], [-1., 0., 2., 0.], [0., -3e-14, 4., 5.], [0., 0., 2., -1.]])
        t = _assert_schur(module, coupled, 2e-8)
        observed = np.sort_complex(np.linalg.eigvals(t) / scale)
        expected = np.sort_complex(np.linalg.eigvals(coupled / scale))
        np.testing.assert_allclose(observed, expected, atol=3e-7)


def test_subnormal_scale_coupled_block_is_not_deflated(module):
    scale = 1e-310
    coupled = np.array([[0., 2.], [-3., 1.]], dtype=np.float64)
    a = scale * coupled

    t, q = map(lambda x: np.asarray(x, dtype=np.float64), module.schur(a))
    assert np.all(np.isfinite(t)) and np.all(np.isfinite(q))
    np.testing.assert_allclose(q.T @ q, np.eye(2), atol=2e-12)

    # Normalize before checking the coupling; raw absolute residuals at this
    # scale are either vacuous or depend on fragile subnormal rounding details.
    normalized_t = t / scale
    np.testing.assert_allclose(q @ normalized_t @ q.T, coupled, atol=2e-12)
    np.testing.assert_allclose(
        np.sort_complex(np.linalg.eigvals(normalized_t)),
        np.sort_complex(np.linalg.eigvals(coupled)),
        atol=2e-12,
    )


def test_single_entry_mutation_is_not_cached(module):
    a = np.array([[1., 4., -2.], [3., 0.5, 1.], [-1., 2., 3.]], dtype=np.float64)
    changed = a.copy()
    changed[1, 0] += 2e-5
    t0 = _assert_schur(module, a, 2e-9)
    t1 = _assert_schur(module, changed, 2e-9)
    eig0 = np.sort_complex(np.linalg.eigvals(t0))
    eig1 = np.sort_complex(np.linalg.eigvals(t1))
    assert np.max(np.abs(eig0 - eig1)) > 1e-7


def test_candidate_reachable_and_scaffold_is_trusted():
    candidate = (FILES / "src" / "francis.rs").read_text()
    scaffold = (FILES / "src" / "lib.rs").read_text()
    assert "francis_double_shift(&mut h" in scaffold
    assert "deflatable(&h" in scaffold
    assert len(candidate.encode()) < 22000
    assert {p.name for p in (FILES / "src").iterdir()} == {"lib.rs", "matrix.rs", "hessenberg.rs", "francis.rs"}
    assert not any(p.is_symlink() for p in (FILES / "src").iterdir())
    forbidden = r"PyModule::import|numpy|scipy|std::process|extern\s+\"C\""
    assert re.search(forbidden, candidate, re.I) is None
