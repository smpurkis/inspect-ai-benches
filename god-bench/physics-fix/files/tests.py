import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np


FILES = Path("/app/files")
APP = Path("/app")
BINARY = APP / "target" / "release" / "gr_sim"
FIXTURES = FILES / "fixtures"


def _stage_project():
    shutil.copyfile(FILES / "Cargo.toml", APP / "Cargo.toml")
    shutil.copytree(FILES / "src", APP / "src", dirs_exist_ok=True)
    shutil.copytree(FILES / "rust_tests", APP / "tests", dirs_exist_ok=True)


def _build():
    _stage_project()
    return subprocess.run(
        ["cargo", "build", "--release", "--offline"],
        capture_output=True,
        text=True,
        cwd=str(APP),
        timeout=300,
    )


def _run_seed(name):
    result = subprocess.run(
        [str(BINARY), "--input", str(FIXTURES / name)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return result.stdout, json.loads(result.stdout)


def _assert_finite(value):
    if isinstance(value, dict):
        for child in value.values():
            _assert_finite(child)
    elif isinstance(value, list):
        for child in value:
            _assert_finite(child)
    elif isinstance(value, (int, float)):
        assert math.isfinite(value)


def test_builds():
    result = _build()
    assert result.returncode == 0, f"cargo build failed:\n{result.stderr[-3000:]}"


def test_public_rust_api_helpers():
    _stage_project()
    result = subprocess.run(
        ["cargo", "test", "--release", "--offline", "--test", "public_api"],
        capture_output=True,
        text=True,
        cwd=str(APP),
        timeout=300,
    )
    assert result.returncode == 0, (
        f"direct Rust API tests failed:\n{result.stdout[-1500:]}\n{result.stderr[-3000:]}"
    )


def test_uniform_tov_smoke():
    assert _build().returncode == 0
    _, payload = _run_seed("seed_tov_uniform.json")
    tov = payload["tov"]
    assert tov["total_mass"] > 0.0 and tov["stellar_radius"] > 0.0
    assert 0.0 < tov["compactness"] < 8.0 / 9.0
    assert len(tov["profile"]) == 50
    pressures = [point["pressure"] for point in tov["profile"]]
    assert all(right <= left + 1e-10 for left, right in zip(pressures, pressures[1:]))


def test_os_collapse_smoke():
    assert _build().returncode == 0
    seed = json.loads((FIXTURES / "seed_os_standard.json").read_text())["collapse"]
    _, payload = _run_seed("seed_os_standard.json")
    collapse = payload["collapse"]
    mass, radius = seed["mass"], seed["initial_radius"]
    expected_singularity = math.pi * math.sqrt(radius**3 / (8.0 * mass))
    np.testing.assert_allclose(collapse["tau_singularity"], expected_singularity, rtol=1e-3)
    np.testing.assert_allclose(collapse["horizon_radius"], 2.0 * mass, rtol=1e-5)
    assert 0.0 < collapse["tau_horizon"] < collapse["tau_singularity"]
    assert len(collapse["trajectory"]) == 51


def test_output_is_finite_and_deterministic():
    assert _build().returncode == 0
    first_stdout, first = _run_seed("seed_os_standard.json")
    second_stdout, second = _run_seed("seed_os_standard.json")
    assert first_stdout == second_stdout
    assert first == second
    _assert_finite(first)


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
