import json
import subprocess
import os

import numpy as np

BINARY = "/app/target/release/nbody_sim"
FIXTURES = "/app/files/fixtures"


def _build():
    result = subprocess.run(
        ["cargo", "build", "--release"],
        capture_output=True,
        text=True,
        cwd="/app",
        timeout=300,
    )
    return result


def _run_sim(seed_file):
    result = subprocess.run(
        [BINARY, "--input", seed_file],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result


def test_trajectory_matches_reference():
    """Build, run, and verify trajectory matches reference within 1e-10."""
    result = _build()
    assert result.returncode == 0, f"cargo build failed:\n{result.stderr[-3000:]}"

    seed = os.path.join(FIXTURES, "seed_01.json")
    ref_file = os.path.join(FIXTURES, "reference_01.json")

    r1 = _run_sim(seed)
    assert r1.returncode == 0, (
        f"Simulator crashed:\nstdout={r1.stdout[:1000]}\nstderr={r1.stderr[:1000]}"
    )

    # Determinism check
    r2 = _run_sim(seed)
    assert r1.stdout == r2.stdout, "Output differs between two runs on the same seed"

    output = json.loads(r1.stdout)
    with open(ref_file) as f:
        reference = json.load(f)

    assert len(output["steps"]) == len(reference["steps"]), (
        f"Step count mismatch: {len(output['steps'])} vs {len(reference['steps'])}"
    )

    for i, (out_step, ref_step) in enumerate(
        zip(output["steps"], reference["steps"])
    ):
        assert abs(out_step["time"] - ref_step["time"]) < 1e-12, (
            f"Time mismatch at step {i}"
        )
        for j, (ob, rb) in enumerate(
            zip(out_step["bodies"], ref_step["bodies"])
        ):
            np.testing.assert_allclose(
                ob["position"],
                rb["position"],
                atol=1e-10,
                err_msg=f"Position mismatch at step {i}, body {j}",
            )
            np.testing.assert_allclose(
                ob["velocity"],
                rb["velocity"],
                atol=1e-10,
                err_msg=f"Velocity mismatch at step {i}, body {j}",
            )


def test_energy_conservation():
    """Total energy must be conserved (drift < 1e-8) on the reference seed."""
    _build()
    seed = os.path.join(FIXTURES, "seed_01.json")
    result = _run_sim(seed)
    assert result.returncode == 0, f"Simulator failed: {result.stderr[:500]}"

    output = json.loads(result.stdout)
    initial_energy = output["steps"][0]["total_energy"]
    final_energy = output["steps"][-1]["total_energy"]
    drift = abs(final_energy - initial_energy)
    assert drift < 1e-8, (
        f"Energy drift {drift:.2e} exceeds tolerance 1e-8 "
        f"(initial={initial_energy}, final={final_energy})"
    )


def test_tunneling_collision_detected():
    _build()
    seed = os.path.join(FIXTURES, "seed_tunneling.json")
    ref_file = os.path.join(FIXTURES, "reference_tunneling.json")

    result = _run_sim(seed)
    assert result.returncode == 0, (
        f"Simulator crashed:\nstdout={result.stdout[:1000]}\nstderr={result.stderr[:1000]}"
    )
    output = json.loads(result.stdout)

    with open(ref_file) as f:
        reference = json.load(f)

    assert output["collisions"], "tunneling collision not detected"
    assert output["collisions"][0]["step"] == reference["collisions"][0]["step"]
    assert abs(output["collisions"][0]["distance"] - reference["collisions"][0]["distance"]) < 1e-10, (
        f"Collision distance mismatch: got {output['collisions'][0]['distance']}, "
        f"expected {reference['collisions'][0]['distance']}"
    )


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(["python3", "-m", "pytest", __file__, "-v"])
    )
