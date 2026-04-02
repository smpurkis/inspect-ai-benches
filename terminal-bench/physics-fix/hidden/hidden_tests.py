import json
import math
import os
import subprocess

import numpy as np

BINARY = "/app/target/release/nbody_sim"
HIDDEN_FIXTURES = "/app/hidden/fixtures"


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
        timeout=120,
    )
    return result


def test_hidden_seed_02_trajectory():
    _build()
    seed = os.path.join(HIDDEN_FIXTURES, "seed_02.json")
    ref_file = os.path.join(HIDDEN_FIXTURES, "reference_02.json")

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
                atol=1e-10,
                err_msg=f"Position mismatch at step {i}, body {j}",
            )
            np.testing.assert_allclose(
                ob["velocity"],
                rb["velocity"],
                atol=1e-10,
                err_msg=f"Velocity mismatch at step {i}, body {j}",
            )


def test_hidden_three_body_stable():
    _build()
    seed = os.path.join(HIDDEN_FIXTURES, "seed_three_body.json")
    ref_file = os.path.join(HIDDEN_FIXTURES, "reference_three_body.json")

    result = _run_sim(seed)
    assert result.returncode == 0, f"Simulator failed: {result.stderr[:500]}"

    output = json.loads(result.stdout)
    with open(ref_file) as f:
        reference = json.load(f)

    # Check all steps were generated
    with open(seed) as f:
        seed_data = json.load(f)
    expected_steps = seed_data["config"]["num_steps"] + 1
    assert len(output["steps"]) == expected_steps, (
        f"Expected {expected_steps} steps, got {len(output['steps'])}"
    )

    # Check energy conservation
    initial_energy = output["steps"][0]["total_energy"]
    final_energy = output["steps"][-1]["total_energy"]
    drift = abs(final_energy - initial_energy)
    assert drift < 1e-6, f"Energy drift too large for three-body: {drift:.2e}"

    # Check checkpoint energies
    for step_str, expected_energy in reference["checkpoint_energies"].items():
        step_num = int(step_str)
        actual_energy = output["steps"][step_num]["total_energy"]
        assert abs(actual_energy - expected_energy) < 1e-10, (
            f"Energy mismatch at step {step_num}: "
            f"expected {expected_energy}, got {actual_energy}"
        )

    # Check bodies remain bounded (no escape)
    for step in output["steps"]:
        for body in step["bodies"]:
            dist = math.sqrt(sum(x * x for x in body["position"]))
            assert dist < 10.0, (
                f"Body escaped: position {body['position']}, distance {dist}"
            )


def test_hidden_collisions_and_tunneling():
    """Collision detection: correct count/details on seed_02 + CCD tunneling on fast approach."""
    _build()

    # Part 1: collision detection on seed_02
    seed_02 = os.path.join(HIDDEN_FIXTURES, "seed_02.json")
    ref_02 = os.path.join(HIDDEN_FIXTURES, "reference_02.json")

    result = _run_sim(seed_02)
    assert result.returncode == 0

    output = json.loads(result.stdout)
    with open(ref_02) as f:
        reference = json.load(f)

    assert len(output["collisions"]) == len(reference["collisions"]), (
        f"Collision count mismatch: {len(output['collisions'])} vs "
        f"{len(reference['collisions'])}"
    )

    for out_col, ref_col in zip(output["collisions"], reference["collisions"]):
        assert out_col["step"] == ref_col["step"]
        assert out_col["body_a"] == ref_col["body_a"]
        assert out_col["body_b"] == ref_col["body_b"]
        assert abs(out_col["distance"] - ref_col["distance"]) < 1e-10

    # Part 2: fast close approach (tunneling)
    seed_tunnel = os.path.join(HIDDEN_FIXTURES, "seed_h_tunnel.json")
    ref_tunnel = os.path.join(HIDDEN_FIXTURES, "reference_h_tunnel.json")

    result = _run_sim(seed_tunnel)
    assert result.returncode == 0, f"Simulator failed: {result.stderr[:500]}"

    output = json.loads(result.stdout)
    with open(ref_tunnel) as f:
        ref_data = json.load(f)

    assert len(output["collisions"]) >= ref_data["collision_count"], (
        f"Expected at least {ref_data['collision_count']} collision(s) "
        f"(tunneling), got {len(output['collisions'])}"
    )

    # End positions must be far apart — bodies tunneled through each other
    final_step = output["steps"][-1]
    pos_a = final_step["bodies"][0]["position"]
    pos_b = final_step["bodies"][1]["position"]
    dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(pos_a, pos_b)))
    assert dist > 1.0, (
        f"Bodies should be far apart after tunneling, but distance={dist:.3f}"
    )


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(["python3", "-m", "pytest", __file__, "-v"])
    )
