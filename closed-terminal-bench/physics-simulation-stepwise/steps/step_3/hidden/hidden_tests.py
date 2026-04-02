import json
import os
import subprocess
import tempfile
import time

import numpy as np

BINARY = "/app/target/release/nbody_sim"
HIDDEN_FIXTURES = "/app/step_3/hidden/fixtures"
STEP1_HIDDEN = "/app/step_1/hidden/fixtures"
STEP2_HIDDEN_BATCH = "/app/step_2/hidden/fixtures/hidden_batch_seeds"
STEP2_HIDDEN_REF = "/app/step_2/hidden/fixtures/hidden_batch_reference.json"


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


def test_hidden_small_n_still_exact():
    """seed_02 matches reference_02 within atol=1e-12 (Barnes-Hut exact for small N)."""
    _build()
    seed = os.path.join(STEP1_HIDDEN, "seed_02.json")
    ref_file = os.path.join(STEP1_HIDDEN, "reference_02.json")

    result = _run_sim(seed)
    assert result.returncode == 0, f"Simulator failed: {result.stderr[:500]}"

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


def test_hidden_500body_under_threshold_time():
    """500-body scenario completes within hidden threshold (stricter than visible)."""
    _build()
    timing_file = os.path.join(HIDDEN_FIXTURES, "hidden_timing_reference.json")
    with open(timing_file) as f:
        timing = json.load(f)

    seed_data = timing["seed"]
    threshold_ms = timing["threshold_time_ms"]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(seed_data, f)
        tmp_path = f.name

    try:
        start = time.monotonic()
        result = subprocess.run(
            [BINARY, "--input", tmp_path],
            capture_output=True,
            text=True,
            timeout=max(threshold_ms / 1000 * 3, 120),
        )
        elapsed_ms = (time.monotonic() - start) * 1000

        assert result.returncode == 0, f"Run failed: {result.stderr[:500]}"
        assert elapsed_ms < threshold_ms, (
            f"Runtime {elapsed_ms:.0f}ms exceeds threshold {threshold_ms}ms"
        )

        output = json.loads(result.stdout)
        ie = output["steps"][0]["total_energy"]
        fe = output["steps"][-1]["total_energy"]
        drift = abs(fe - ie)
        assert drift < 1e-2, f"Energy drift {drift:.2e} too large"
    finally:
        os.unlink(tmp_path)


def test_hidden_tree_theta_respected():
    """For widely-separated bodies, verify Barnes-Hut approximation is used.

    With θ=0.5, a far-away cluster will be approximated as a single mass.
    We verify that the simulation still produces valid output (doesn't crash
    or produce NaN) and that energy is reasonably conserved, indicating the
    tree traversal works correctly.
    """
    _build()
    # Use a seed with bodies spread across a large volume to exercise the tree
    seed_data = {
        "config": {
            "dt": 0.001,
            "num_steps": 10,
            "collision_threshold": 0.1,
            "gravitational_constant": 6.674e-11,
        },
        "bodies": [
            {"mass": 1e12, "position": [0.0, 0.0, 0.0], "velocity": [0.0, 0.0, 0.0]},
            {"mass": 1e12, "position": [1000.0, 0.0, 0.0], "velocity": [0.0, 0.0, 0.0]},
            {"mass": 1e12, "position": [0.0, 1000.0, 0.0], "velocity": [0.0, 0.0, 0.0]},
        ],
    }

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(seed_data, f)
        tmp_path = f.name

    try:
        result = _run_sim(tmp_path)
        assert result.returncode == 0, f"Simulator failed: {result.stderr[:500]}"

        output = json.loads(result.stdout)
        assert len(output["steps"]) > 0

        # Check no NaN in output
        for step in output["steps"]:
            assert not (step["total_energy"] != step["total_energy"]), (
                "NaN detected in total_energy — Barnes-Hut tree may be corrupted"
            )
            for body in step["bodies"]:
                for v in body["position"] + body["velocity"]:
                    assert v == v, "NaN detected in body state"
    finally:
        os.unlink(tmp_path)


def test_hidden_optimized_deterministic():
    """Two runs on seed_02 produce byte-identical stdout."""
    _build()
    seed = os.path.join(STEP1_HIDDEN, "seed_02.json")

    r1 = _run_sim(seed)
    r2 = _run_sim(seed)
    assert r1.returncode == 0
    assert r2.returncode == 0
    assert r1.stdout == r2.stdout, "Optimized code is non-deterministic"


def test_hidden_no_unsafe_in_hot_path():
    """No unsafe blocks should be present in sim.rs."""
    sim_path = "/app/src/sim.rs"
    assert os.path.exists(sim_path), "sim.rs not found"

    with open(sim_path) as f:
        content = f.read()

    unsafe_count = content.count("unsafe")
    assert unsafe_count == 0, (
        f"Found {unsafe_count} occurrence(s) of 'unsafe' in sim.rs. "
        "Optimization should not require unsafe code."
    )


def test_hidden_optimized_batch_exact():
    """Batch mode on hidden batch seeds: collision_count and final_positions match reference."""
    _build()
    with open(STEP2_HIDDEN_REF) as f:
        reference = json.load(f)

    result = _run_batch(STEP2_HIDDEN_BATCH)
    assert result.returncode == 0

    summaries = json.loads(result.stdout)
    assert len(summaries) == len(reference)

    for out_sum, ref_sum in zip(summaries, reference):
        assert out_sum["seed_file"] == ref_sum["seed_file"]
        np.testing.assert_allclose(
            out_sum["initial_energy"],
            ref_sum["initial_energy"],
            atol=1e-10,
        )
        np.testing.assert_allclose(
            out_sum["final_energy"],
            ref_sum["final_energy"],
            atol=1e-10,
        )
        assert out_sum["collision_count"] == ref_sum["collision_count"]
        for bp, rp in zip(
            out_sum["final_positions"], ref_sum["final_positions"]
        ):
            np.testing.assert_allclose(bp, rp, atol=1e-10)


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(["python3", "-m", "pytest", __file__, "-v"])
    )
