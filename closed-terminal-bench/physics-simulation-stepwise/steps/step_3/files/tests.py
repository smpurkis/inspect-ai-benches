import json
import os
import subprocess
import time

import numpy as np

BINARY = "/app/target/release/nbody_sim"
FIXTURES = "/app/step_3/files/fixtures"
STEP1_FIXTURES = "/app/step_1/files/fixtures"
STEP2_BATCH = "/app/step_2/files/fixtures/batch_seeds"
STEP2_REF = "/app/step_2/files/fixtures/reference_batch_summaries.json"


def _build():
    result = subprocess.run(
        ["cargo", "build", "--release"],
        capture_output=True,
        text=True,
        cwd="/app",
        timeout=300,
    )
    assert result.returncode == 0, f"Build failed:\n{result.stderr[-2000:]}"


def _run_sim(seed_file):
    result = subprocess.run(
        [BINARY, "--input", seed_file],
        capture_output=True,
        text=True,
        timeout=300,
    )
    return result


def _run_batch(seed_dir):
    result = subprocess.run(
        [BINARY, "--batch", "--input", seed_dir],
        capture_output=True,
        text=True,
        timeout=300,
    )
    return result


def test_optimized_builds():
    _build()


def test_small_n_still_exact():
    """seed_01 output matches reference_01.json within atol=1e-12."""
    _build()
    seed = os.path.join(STEP1_FIXTURES, "seed_01.json")
    ref_file = os.path.join(STEP1_FIXTURES, "reference_01.json")

    result = _run_sim(seed)
    assert result.returncode == 0

    output = json.loads(result.stdout)
    with open(ref_file) as f:
        reference = json.load(f)

    assert len(output["steps"]) == len(reference["steps"])

    for i, (out_step, ref_step) in enumerate(
        zip(output["steps"], reference["steps"])
    ):
        for j, (ob, rb) in enumerate(
            zip(out_step["bodies"], ref_step["bodies"])
        ):
            np.testing.assert_allclose(
                ob["position"],
                rb["position"],
                atol=1e-12,
                err_msg=f"Position mismatch at step {i}, body {j}",
            )
            np.testing.assert_allclose(
                ob["velocity"],
                rb["velocity"],
                atol=1e-12,
                err_msg=f"Velocity mismatch at step {i}, body {j}",
            )

    assert len(output["collisions"]) == len(reference["collisions"])


def test_500body_timing():
    """seed_500body runs in < threshold_ms from timing_baseline.json."""
    _build()
    timing_file = os.path.join(FIXTURES, "timing_baseline.json")
    with open(timing_file) as f:
        timing = json.load(f)

    threshold_ms = timing["threshold_ms"]
    seed_file = os.path.join(FIXTURES, timing["seed_file"])

    start = time.monotonic()
    result = subprocess.run(
        [BINARY, "--input", seed_file],
        capture_output=True,
        text=True,
        timeout=max(threshold_ms / 1000 * 5, 120),
    )
    elapsed_ms = (time.monotonic() - start) * 1000

    assert result.returncode == 0, f"500-body run failed: {result.stderr[:500]}"
    assert elapsed_ms < threshold_ms, (
        f"Runtime {elapsed_ms:.0f}ms exceeds threshold {threshold_ms}ms"
    )

    output = json.loads(result.stdout)
    assert len(output["steps"]) > 0


def test_optimized_energy_conservation():
    """seed_01 energy drift < 1e-8."""
    _build()
    seed = os.path.join(STEP1_FIXTURES, "seed_01.json")
    result = _run_sim(seed)
    assert result.returncode == 0

    output = json.loads(result.stdout)
    initial_energy = output["steps"][0]["total_energy"]
    final_energy = output["steps"][-1]["total_energy"]
    drift = abs(final_energy - initial_energy)
    assert drift < 1e-8, f"Energy drift too large: {drift:.2e}"


def test_500body_runs_without_crash():
    """seed_500body exits 0 and produces valid JSON."""
    _build()
    timing_file = os.path.join(FIXTURES, "timing_baseline.json")
    with open(timing_file) as f:
        timing = json.load(f)

    seed_file = os.path.join(FIXTURES, timing["seed_file"])

    result = subprocess.run(
        [BINARY, "--input", seed_file],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"500-body run crashed: {result.stderr[:500]}"

    output = json.loads(result.stdout)
    assert "steps" in output
    assert "collisions" in output
    assert len(output["steps"]) > 0


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(["python3", "-m", "pytest", __file__, "-v"])
    )
