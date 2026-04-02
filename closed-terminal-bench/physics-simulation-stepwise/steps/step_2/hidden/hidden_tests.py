import json
import os
import subprocess
import tempfile

import numpy as np

BINARY = "/app/target/release/nbody_sim"
HIDDEN_FIXTURES = "/app/step_2/hidden/fixtures"
HIDDEN_BATCH_SEEDS = os.path.join(HIDDEN_FIXTURES, "hidden_batch_seeds")


def _build():
    result = subprocess.run(
        ["cargo", "build", "--release"],
        capture_output=True,
        text=True,
        cwd="/app",
        timeout=300,
    )
    assert result.returncode == 0, f"Build failed:\n{result.stderr[-2000:]}"


def _run_batch(seed_dir, output_file=None):
    cmd = [BINARY, "--batch", "--input", seed_dir]
    if output_file:
        cmd.extend(["--output", output_file])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return result


def _run_single(seed_file):
    result = subprocess.run(
        [BINARY, "--input", seed_file],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result


def test_hidden_adaptive_steps_counted():
    """Hidden batch seeds with close-encounter scenarios: actual_steps > num_steps."""
    _build()
    ref_file = os.path.join(HIDDEN_FIXTURES, "hidden_batch_reference.json")
    with open(ref_file) as f:
        reference = json.load(f)

    result = _run_batch(HIDDEN_BATCH_SEEDS)
    assert result.returncode == 0, f"Batch failed:\n{result.stderr[:1000]}"

    summaries = json.loads(result.stdout)
    assert len(summaries) == len(reference), (
        f"Expected {len(reference)} summaries, got {len(summaries)}"
    )

    # All summaries must have actual_steps field
    for summary in summaries:
        assert "actual_steps" in summary, (
            f"{summary['seed_file']}: missing 'actual_steps' field"
        )
        assert summary["actual_steps"] >= summary["num_steps"], (
            f"{summary['seed_file']}: actual_steps ({summary['actual_steps']}) "
            f"< num_steps ({summary['num_steps']})"
        )


def test_hidden_adaptive_same_collision_outcome():
    """Collision detection must be unchanged by adaptive stepping."""
    _build()
    ref_file = os.path.join(HIDDEN_FIXTURES, "hidden_batch_reference.json")
    with open(ref_file) as f:
        reference = json.load(f)

    result = _run_batch(HIDDEN_BATCH_SEEDS)
    assert result.returncode == 0

    summaries = json.loads(result.stdout)
    ref_by_name = {r["seed_file"]: r for r in reference}

    for summary in summaries:
        name = summary["seed_file"]
        if name in ref_by_name:
            expected = ref_by_name[name]["collision_count"]
            assert summary["collision_count"] == expected, (
                f"{name}: collision_count {summary['collision_count']} != {expected}"
            )


def test_hidden_energy_better_with_adaptive():
    """Energy drift for close-encounter seed must be < 1e-4 with adaptive stepping."""
    _build()
    result = _run_batch(HIDDEN_BATCH_SEEDS)
    assert result.returncode == 0

    summaries = json.loads(result.stdout)
    for summary in summaries:
        assert summary["energy_drift"] < 1e-4, (
            f"{summary['seed_file']}: energy drift {summary['energy_drift']:.2e} too large"
        )


def test_hidden_collision_near_miss():
    """Near-miss scenario: bodies come close but don't collide; actual_steps >= num_steps."""
    _build()
    seed_file = os.path.join(HIDDEN_BATCH_SEEDS, "seed_h4.json")
    result = _run_single(seed_file)
    assert result.returncode == 0

    output = json.loads(result.stdout)
    assert len(output["collisions"]) == 0, (
        f"Near-miss should have 0 collisions, got {len(output['collisions'])}"
    )


def test_hidden_summary_ordering():
    """Summaries must be sorted by seed_file name."""
    _build()
    result = _run_batch(HIDDEN_BATCH_SEEDS)
    assert result.returncode == 0

    summaries = json.loads(result.stdout)
    names = [s["seed_file"] for s in summaries]
    assert names == sorted(names), (
        f"Summaries not sorted by filename: {names}"
    )


def test_hidden_empty_batch_handled():
    """Empty input directory produces empty JSON array."""
    _build()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_batch(tmpdir)
        assert result.returncode == 0, (
            f"Empty batch should succeed:\n{result.stderr[:500]}"
        )
        summaries = json.loads(result.stdout)
        assert summaries == [], f"Expected empty array, got: {summaries}"


def test_hidden_malformed_seed_rejected():
    """Malformed seed file produces error, not crash."""
    _build()
    with tempfile.TemporaryDirectory() as tmpdir:
        bad_file = os.path.join(tmpdir, "bad_seed.json")
        with open(bad_file, "w") as f:
            f.write("{not valid json!!!")

        result = _run_batch(tmpdir)
        assert "panic" not in result.stderr.lower(), (
            f"Simulator panicked on bad input: {result.stderr[:500]}"
        )


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(["python3", "-m", "pytest", __file__, "-v"])
    )
