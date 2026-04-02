import json
import subprocess
import os

import numpy as np

BINARY = "/app/target/release/nbody_sim"
FIXTURES = "/app/step_1/files/fixtures"


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


def test_binary_builds():
    result = _build()
    assert result.returncode == 0, f"cargo build failed:\n{result.stderr[-3000:]}"


def test_runs_without_crash():
    _build()
    seed = os.path.join(FIXTURES, "seed_01.json")
    result = _run_sim(seed)
    assert result.returncode == 0, (
        f"Simulator crashed:\nstdout={result.stdout[:1000]}\nstderr={result.stderr[:1000]}"
    )


def test_deterministic_two_runs():
    _build()
    seed = os.path.join(FIXTURES, "seed_01.json")
    r1 = _run_sim(seed)
    r2 = _run_sim(seed)
    assert r1.returncode == 0, f"Run 1 failed: {r1.stderr[:500]}"
    assert r2.returncode == 0, f"Run 2 failed: {r2.stderr[:500]}"
    assert r1.stdout == r2.stdout, "Output differs between two runs on the same seed"


def test_trajectory_matches_reference():
    _build()
    seed = os.path.join(FIXTURES, "seed_01.json")
    ref_file = os.path.join(FIXTURES, "reference_01.json")

    result = _run_sim(seed)
    assert result.returncode == 0, f"Simulator failed: {result.stderr[:500]}"

    output = json.loads(result.stdout)
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


def test_output_format_valid_json():
    _build()
    seed = os.path.join(FIXTURES, "seed_01.json")
    result = _run_sim(seed)
    assert result.returncode == 0

    output = json.loads(result.stdout)
    assert "steps" in output, "Missing 'steps' key"
    assert "collisions" in output, "Missing 'collisions' key"
    assert isinstance(output["steps"], list)
    assert len(output["steps"]) > 0

    step = output["steps"][0]
    for key in ("time", "bodies", "total_energy"):
        assert key in step, f"Missing '{key}' in step record"

    body = step["bodies"][0]
    for key in ("position", "velocity", "ke", "pe"):
        assert key in body, f"Missing '{key}' in body state"
    assert len(body["position"]) == 3
    assert len(body["velocity"]) == 3


def test_tunneling_collision_detected():
    _build()
    seed = os.path.join(FIXTURES, "seed_tunneling.json")
    result = _run_sim(seed)
    assert result.returncode == 0, (
        f"Simulator crashed:\nstdout={result.stdout[:1000]}\nstderr={result.stderr[:1000]}"
    )
    output = json.loads(result.stdout)
    assert output["collisions"], "tunneling collision not detected"
    assert output["collisions"][0]["step"] == 0


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(["python3", "-m", "pytest", __file__, "-v"])
    )
