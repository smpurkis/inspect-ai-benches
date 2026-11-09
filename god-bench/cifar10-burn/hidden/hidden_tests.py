import math
import random
import re
import subprocess
from pathlib import Path

import pytest

FILES = Path("/app/files") if Path("/app/files").exists() else Path(__file__).resolve().parents[1] / "files"
ROOT = FILES / "cifar-infer"
BIN = ROOT / "target" / "release" / "policy-probe"
MASK = (1 << 64) - 1


@pytest.fixture(scope="session", autouse=True)
def build():
    lock = Path("/opt/cifar-infer-Cargo.lock")
    if lock.exists():
        (ROOT / "Cargo.lock").write_bytes(lock.read_bytes())
    result = subprocess.run(["cargo", "build", "--release", "--locked", "--offline"], cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stderr[-4000:]


def probe(*args, ok=True):
    result = subprocess.run([BIN, *map(str, args)], capture_output=True, text=True, timeout=20)
    assert (result.returncode == 0) is ok
    return result.stdout.strip()


def mix64(value):
    value ^= value >> 30
    value = (value * 0xBF58476D1CE4E5B9) & MASK
    value ^= value >> 27
    value = (value * 0x94D049BB133111EB) & MASK
    return value ^ (value >> 31)


def expected_augmentation(seed, epoch, sample):
    rotated = ((epoch << 32) | (epoch >> 32)) & MASK
    bits = mix64(seed ^ ((sample * 0x9E3779B97F4A7C15) & MASK) ^ rotated)
    return int(bits & 1), ((bits >> 1) % 9) - 4, ((bits >> 8) % 9) - 4


def test_generated_augmentation_every_field_and_metamorphism():
    rng = random.Random(7719)
    seen = set()
    for _ in range(180):
        case = (rng.getrandbits(64), rng.randrange(1 << 32), rng.getrandbits(64))
        actual = tuple(map(int, probe("augment", *case).split(",")))
        assert actual == expected_augmentation(*case)
        seen.add(actual)
    assert len(seen) > 80
    assert probe("augment", 4, 3, 2) != probe("augment", 4, 3, 3)


def expected_lr(base, epoch, total):
    warmup = min(5, total)
    if epoch == total:
        return 0.0
    if epoch < warmup:
        return base * (epoch + 1) / warmup
    progress = (epoch - (warmup - 1)) / (total - (warmup - 1))
    return base * 0.5 * (1.0 + math.cos(math.pi * progress))


def test_generated_schedule_boundaries_monotonicity_and_scaling():
    for total in (1, 2, 5, 6, 17, 100):
        actual = [float(probe("lr", 0.37, epoch, total)) for epoch in range(total + 1)]
        expected = [expected_lr(0.37, epoch, total) for epoch in range(total + 1)]
        assert actual == pytest.approx(expected, abs=2e-15)
        peak = min(5, total) - 1
        assert actual[:peak + 1] == sorted(actual[:peak + 1])
        assert actual[peak:] == sorted(actual[peak:], reverse=True)
        scaled = [float(probe("lr", 0.74, epoch, total)) for epoch in range(total + 1)]
        assert scaled == pytest.approx([2 * value for value in actual])
    for args in ((0, 0, 2), (-1, 0, 2), (0.1, 3, 2), (0.1, 0, 0), (float("nan"), 0, 2)):
        probe("lr", *args, ok=False)


def test_generated_class_weights_balance_and_permutation():
    rng = random.Random(8821)
    for _ in range(60):
        counts = [rng.randrange(1, 10000) for _ in range(10)]
        actual = list(map(float, probe("weights", *counts).split(",")))
        total = sum(counts)
        expected = [total / (10 * count) for count in counts]
        assert actual == pytest.approx(expected, rel=2e-15)
        assert sum(count * weight for count, weight in zip(counts, actual)) == pytest.approx(total)
        rotated = counts[3:] + counts[:3]
        rotated_weights = list(map(float, probe("weights", *rotated).split(",")))
        assert rotated_weights == pytest.approx(expected[3:] + expected[:3])
    probe("weights", 0, *([1] * 9), ok=False)


def test_checkpoint_total_order_and_invalid_metrics():
    assert probe("checkpoint-none", 0.0, 9.0, 99) == "true"
    cases = [
        ((0.8, 2.0, 9), (0.7, 0.1, 1), True),
        ((0.8, 1.0, 9), (0.8, 2.0, 1), True),
        ((0.8, 1.0, 4), (0.8, 1.0, 5), True),
        ((0.8, 1.0, 5), (0.8, 1.0, 5), False),
        ((0.7, 0.1, 1), (0.8, 9.0, 99), False),
    ]
    for candidate, current, expected in cases:
        assert probe("checkpoint", *candidate, *current) == str(expected).lower()
    probe("checkpoint", "NaN", 1, 1, 0.5, 1, 2, ok=False)


def test_scaffold_inventory_and_kernel_reachability():
    expected = {
        "TASK.md", "contract.toml", "instructions.md", "tests.py",
        "cifar-infer/Cargo.toml", "cifar-infer/src/main.rs", "cifar-infer/src/model.rs",
        "cifar-infer/src/policy_probe.rs", "cifar-infer/src/trainer.rs", "cifar-infer/src/training_policy.rs",
    }
    found = set()
    for path in FILES.rglob("*"):
        relative = path.relative_to(FILES)
        if relative.parts[0] in {"__pycache__", ".pytest_cache"} or "target" in relative.parts or path.name == "Cargo.lock" or path.suffix == ".pyc":
            continue
        assert not path.is_symlink()
        if path.is_file():
            found.add(relative.as_posix())
    assert found == expected
    probe_source = (ROOT / "src/policy_probe.rs").read_text()
    trainer_source = (ROOT / "src/trainer.rs").read_text()
    for name in ("augmentation", "learning_rate", "class_weights", "prefer_checkpoint"):
        assert name in probe_source
    assert "augmentation" in trainer_source and "class_weights" in trainer_source
    source = (ROOT / "src/training_policy.rs").read_text()
    assert 500 < len(source) < 18000
    assert re.search(r"\b(?:rand|thread_rng|SystemTime|Instant)\b", source) is None
