import math
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent / "cifar-infer"
BIN = ROOT / "target" / "release" / "policy-probe"


@pytest.fixture(scope="session", autouse=True)
def build():
    lock = Path("/opt/cifar-infer-Cargo.lock")
    if lock.exists():
        (ROOT / "Cargo.lock").write_bytes(lock.read_bytes())
    result = subprocess.run(["cargo", "build", "--release", "--locked", "--offline"], cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stderr[-4000:]


def probe(*args):
    result = subprocess.run([BIN, *map(str, args)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_normal_augmentation_uses_seed_epoch_and_sample():
    values = {probe("augment", 17, epoch, sample) for epoch in range(3) for sample in range(8)}
    assert len(values) >= 8
    for value in values:
        flip, x, y = map(int, value.split(","))
        assert flip in (0, 1) and -4 <= x <= 4 and -4 <= y <= 4


def test_edge_schedule_finishes_at_zero():
    assert float(probe("lr", 0.2, 20, 20)) == 0.0
    assert float(probe("lr", 0.2, 0, 20)) <= 0.2


def test_invariant_balanced_classes_have_unit_weights():
    weights = [float(value) for value in probe("weights", *([12] * 10)).split(",")]
    assert weights == [1.0] * 10


def test_deterministic_checkpoint_and_policy_rerun():
    first = probe("augment", 999, 4, 81)
    assert first == probe("augment", 999, 4, 81)
    assert probe("checkpoint", 0.9, 0.5, 8, 0.8, 0.1, 2) == "true"
