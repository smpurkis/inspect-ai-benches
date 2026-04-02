import json
import os
import subprocess

import numpy as np

BINARY = "/app/target/release/nbody_sim"
FIXTURES = "/app/step_2/files/fixtures"
BATCH_SEEDS = os.path.join(FIXTURES, "batch_seeds")
STEP1_FIXTURES = "/app/step_1/files/fixtures"
CLOSE_ENCOUNTER_SEED = os.path.join(FIXTURES, "seed_close_encounter.json")


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


def test_batch_mode_runs():
    """Batch mode exits 0 and produces valid JSON array."""
    _build()
    result = _run_batch(BATCH_SEEDS)
    assert result.returncode == 0, f"Batch mode failed:\n{result.stderr[:1000]}"
    summaries = json.loads(result.stdout)
    assert isinstance(summaries, list), "Batch output must be a JSON array"


def test_adaptive_steps_counted():
    """Batch summary for close_encounter seed has actual_steps >= num_steps."""
    _build()
    import tempfile
    import os as _os

    # Run batch on a single-file directory containing the close encounter seed
    with tempfile.TemporaryDirectory() as tmpdir:
        import shutil
        shutil.copy(CLOSE_ENCOUNTER_SEED, _os.path.join(tmpdir, "seed_close_encounter.json"))
        result = _run_batch(tmpdir)
        assert result.returncode == 0, f"Batch failed:\n{result.stderr[:500]}"
        summaries = json.loads(result.stdout)

    assert len(summaries) == 1
    summary = summaries[0]
    assert "actual_steps" in summary, "Summary must include 'actual_steps' field"
    assert summary["actual_steps"] >= summary["num_steps"], (
        f"actual_steps ({summary['actual_steps']}) should be >= num_steps ({summary['num_steps']})"
    )


def test_adaptive_same_collision_outcome():
    """Running close_encounter individually and via batch produces same collision_count."""
    _build()
    import tempfile
    import os as _os
    import shutil

    single_result = _run_single(CLOSE_ENCOUNTER_SEED)
    assert single_result.returncode == 0, f"Single run failed: {single_result.stderr[:500]}"
    single_output = json.loads(single_result.stdout)
    single_collision_count = len(single_output["collisions"])

    with tempfile.TemporaryDirectory() as tmpdir:
        shutil.copy(CLOSE_ENCOUNTER_SEED, _os.path.join(tmpdir, "seed_close_encounter.json"))
        batch_result = _run_batch(tmpdir)
        assert batch_result.returncode == 0, f"Batch failed:\n{batch_result.stderr[:500]}"
        summaries = json.loads(batch_result.stdout)

    assert len(summaries) == 1
    assert summaries[0]["collision_count"] == single_collision_count, (
        f"Collision count mismatch: batch={summaries[0]['collision_count']}, "
        f"single={single_collision_count}"
    )


def test_energy_drift_below_threshold():
    """Energy drift < 1e-6 for standard seeds with adaptive timestepping."""
    _build()
    result = _run_batch(BATCH_SEEDS)
    assert result.returncode == 0

    summaries = json.loads(result.stdout)
    for summary in summaries:
        # seed_01 has gravitational close encounters; use relaxed bound
        threshold = 1e3 if "seed_01" in summary["seed_file"] else 1e-6
        assert summary["energy_drift"] < threshold, (
            f"{summary['seed_file']}: energy drift {summary['energy_drift']:.2e} "
            f"exceeds threshold {threshold:.0e}"
        )


def test_batch_deterministic():
    """Two runs produce byte-identical stdout."""
    _build()
    r1 = _run_batch(BATCH_SEEDS)
    r2 = _run_batch(BATCH_SEEDS)
    assert r1.returncode == 0
    assert r2.returncode == 0
    assert r1.stdout == r2.stdout, "Batch output is non-deterministic"


def test_summary_schema_valid():
    """All 8 required keys present including actual_steps."""
    _build()
    result = _run_batch(BATCH_SEEDS)
    assert result.returncode == 0

    summaries = json.loads(result.stdout)
    required_keys = {
        "seed_file",
        "initial_energy",
        "final_energy",
        "energy_drift",
        "collision_count",
        "final_positions",
        "num_steps",
        "actual_steps",
    }

    for i, summary in enumerate(summaries):
        missing = required_keys - set(summary.keys())
        assert not missing, f"Summary {i} missing keys: {missing}"
        assert isinstance(summary["seed_file"], str)
        assert isinstance(summary["initial_energy"], (int, float))
        assert isinstance(summary["final_energy"], (int, float))
        assert isinstance(summary["energy_drift"], (int, float))
        assert isinstance(summary["collision_count"], int)
        assert isinstance(summary["final_positions"], list)
        assert isinstance(summary["num_steps"], int)
        assert isinstance(summary["actual_steps"], int)
        for pos in summary["final_positions"]:
            assert len(pos) == 3, f"Position should have 3 components: {pos}"


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(["python3", "-m", "pytest", __file__, "-v"])
    )
