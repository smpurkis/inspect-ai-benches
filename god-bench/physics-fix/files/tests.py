import subprocess
from pathlib import Path

FILES = Path("/app/files")
APP = Path("/app")


def _run(name):
    subprocess.run(["rm", "-rf", str(APP / "src"), str(APP / "tests")], check=True)
    subprocess.run(["cp", "-r", str(FILES / "src"), str(APP / "src")], check=True)
    subprocess.run(["cp", "-r", str(FILES / "tests"), str(APP / "tests")], check=True)
    subprocess.run(["cp", str(FILES / "Cargo.toml"), str(APP / "Cargo.toml")], check=True)
    result = subprocess.run(
        ["cargo", "test", "--release", "--offline", name, "--", "--exact"],
        cwd=APP, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-3000:]


def test_normal_case():
    _run("normal_pressure_zero_uses_dense_state")


def test_edge_case():
    _run("edge_endpoint_and_direction_are_respected")


def test_invariant():
    _run("invariant_physical_events_return_consistent_states")


def test_deterministic_rerun():
    _run("deterministic_rerun_is_bitwise_equal")
