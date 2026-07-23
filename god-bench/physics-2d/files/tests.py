"""Compact public smoke suite for the deterministic 2D physics CLI."""

import json
import math
import os
import subprocess
import tempfile


SCRIPT = "/app/files/physics2d.py"
STATE_KEYS = ("x", "y", "vx", "vy", "angle", "omega")


def run_sim(config: dict, steps: int, *, timeout=60):
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as cf:
        json.dump(config, cf)
        config_path = cf.name
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as output_file:
        output_path = output_file.name
    try:
        result = subprocess.run(
            [
                "python3",
                SCRIPT,
                "--config",
                config_path,
                "--output",
                output_path,
                "--steps",
                str(steps),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        assert result.returncode == 0, result.stderr
        with open(output_path, encoding="utf-8") as output:
            lines = output.read().splitlines()
        assert len(lines) == steps
        return [json.loads(line) for line in lines]
    finally:
        os.unlink(config_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def body(
    id=0,
    x=50.0,
    y=50.0,
    vx=0.0,
    vy=0.0,
    angle=0.0,
    omega=0.0,
    mass=1.0,
    w=2.0,
    h=2.0,
    e=1.0,
    mu=0.0,
):
    return {
        "id": id,
        "x": x,
        "y": y,
        "vx": vx,
        "vy": vy,
        "angle": angle,
        "omega": omega,
        "mass": mass,
        "w": w,
        "h": h,
        "e": e,
        "mu": mu,
    }


def config(bodies, width=200.0, height=200.0, dt=0.01, g=0.0):
    return {
        "width": width,
        "height": height,
        "dt": dt,
        "g": g,
        "solver_iterations": 10,
        "bodies": bodies,
    }


def test_cli_writes_requested_step_count():
    assert os.path.isfile(SCRIPT), f"{SCRIPT} not found"
    records = run_sim(config([body()]), 4)
    assert [record["step"] for record in records] == [0, 1, 2, 3]


def test_output_schema_and_body_order():
    records = run_sim(config([body(id=2), body(id=0, x=20.0)]), 2)
    for step, record in enumerate(records):
        assert set(record) == {"step", "bodies"}
        assert record["step"] == step
        assert [item["id"] for item in record["bodies"]] == [0, 2]
        for item in record["bodies"]:
            assert set(item) == {"id", *STATE_KEYS}
            for key in STATE_KEYS:
                assert type(item[key]) in (int, float) and math.isfinite(item[key])
                assert item[key] == round(item[key], 6)


def test_free_motion():
    records = run_sim(
        config(
            [body(x=100.0, y=100.0, vx=5.0, vy=-3.0, angle=0.5, omega=2.0)],
            width=1000.0,
            height=1000.0,
            dt=0.1,
        ),
        5,
    )
    for index, record in enumerate(records, start=1):
        state = record["bodies"][0]
        assert abs(state["x"] - (100.0 + 0.5 * index)) < 1e-4
        assert abs(state["y"] - (100.0 - 0.3 * index)) < 1e-4
        assert abs(state["angle"] - (0.5 + 0.2 * index)) < 1e-4
        assert state["vx"] == 5.0 and state["vy"] == -3.0 and state["omega"] == 2.0


def test_basic_wall_collision():
    records = run_sim(
        config([body(x=25.0, vx=10.0)], width=30.0, height=100.0, dt=0.1),
        10,
    )
    velocities = [record["bodies"][0]["vx"] for record in records]
    assert any(vx < 0 for vx in velocities)
    assert all(abs(abs(vx) - 10.0) < 0.5 for vx in velocities)


def test_basic_body_contact():
    bodies = [
        body(id=0, x=49.0, y=100.0, vx=10.0),
        body(id=1, x=51.0, y=100.0, vx=-10.0),
    ]
    state = run_sim(config(bodies, dt=0.01), 1)[0]["bodies"]
    assert state[0]["vx"] < -9.0
    assert state[1]["vx"] > 9.0
    assert state[0]["x"] < state[1]["x"]


def test_deterministic():
    simulation = config(
        [
            body(id=0, x=20.0, vx=5.0, omega=1.0),
            body(id=1, x=80.0, vx=-3.0, mass=2.0, w=3.0, h=3.0),
        ],
        g=9.81,
    )
    assert run_sim(simulation, 20) == run_sim(simulation, 20)
