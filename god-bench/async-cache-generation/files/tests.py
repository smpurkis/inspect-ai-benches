import subprocess

import pytest

CLASSES = "/tmp/async-cache-generation-build/classes"


@pytest.mark.parametrize("case", ["normal", "edge", "invariant", "deterministic"])
def test_public_cache_semantics(case):
    result = subprocess.run(
        ["java", "-ea", "-cp", CLASSES, "cache.PublicTests", case],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
