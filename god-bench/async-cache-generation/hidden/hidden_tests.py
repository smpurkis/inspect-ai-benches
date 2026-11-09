import subprocess


def test_hidden_deterministic_interleavings():
    result = subprocess.run(
        ["bash", "/app/hidden/run_hidden.sh"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
