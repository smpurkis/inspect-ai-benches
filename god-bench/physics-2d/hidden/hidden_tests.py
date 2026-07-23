"""Hidden tests for physics-2d: advanced physics correctness checks.

These tests are NOT visible to the agent. They verify OBB collision detection,
rotational dynamics, conservation laws, friction, multi-body stability,
accumulated impulse clamping, velocity-dependent restitution, position
correction, and circle-rectangle collision handling.
"""

import json
import math
import os
import subprocess
import tempfile

import pytest

SCRIPT = "/app/files/physics2d.py"

CONFIG_KEYS = {"width", "height", "dt", "g", "solver_iterations", "bodies"}
REQUIRED_CONFIG_KEYS = {"width", "height", "dt", "g", "bodies"}
BODY_KEYS = {
    "id", "x", "y", "vx", "vy", "angle", "omega", "mass",
    "shape", "w", "h", "r", "e", "mu",
}
REQUIRED_BODY_KEYS = {"id", "x", "y", "vx", "vy", "mass"}
OUTPUT_BODY_KEYS = {"id", "x", "y", "vx", "vy", "angle", "omega"}
STATE_KEYS = ("x", "y", "vx", "vy", "angle", "omega")


def _is_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _require_number(value, path, *, positive=False, minimum=None, maximum=None):
    assert _is_number(value), f"{path} must be a finite JSON number"
    if positive:
        assert value > 0, f"{path} must be > 0"
    if minimum is not None:
        assert value >= minimum, f"{path} must be >= {minimum}"
    if maximum is not None:
        assert value <= maximum, f"{path} must be <= {maximum}"


def validate_config(config):
    """Validate the schema.json input subset without requiring jsonschema."""
    assert type(config) is dict, "config must be an object"
    assert REQUIRED_CONFIG_KEYS <= set(config), "config is missing required properties"
    assert set(config) <= CONFIG_KEYS, f"unexpected config properties: {set(config) - CONFIG_KEYS}"
    _require_number(config["width"], "width", positive=True)
    _require_number(config["height"], "height", positive=True)
    _require_number(config["dt"], "dt", positive=True)
    _require_number(config["g"], "g")
    if "solver_iterations" in config:
        assert type(config["solver_iterations"]) is int
        assert config["solver_iterations"] >= 1
    assert type(config["bodies"]) is list

    ids = []
    for index, body in enumerate(config["bodies"]):
        path = f"bodies[{index}]"
        assert type(body) is dict, f"{path} must be an object"
        assert REQUIRED_BODY_KEYS <= set(body), f"{path} is missing required properties"
        assert set(body) <= BODY_KEYS, f"{path} has unexpected properties"
        assert type(body["id"]) is int, f"{path}.id must be an integer"
        ids.append(body["id"])
        for key in ("x", "y", "vx", "vy"):
            _require_number(body[key], f"{path}.{key}")
        _require_number(body["mass"], f"{path}.mass", positive=True)
        for key in ("angle", "omega"):
            if key in body:
                _require_number(body[key], f"{path}.{key}")
        if "e" in body:
            _require_number(body["e"], f"{path}.e", minimum=0, maximum=1)
        if "mu" in body:
            _require_number(body["mu"], f"{path}.mu", minimum=0)

        shape = body.get("shape", "rect")
        assert shape in ("rect", "circle"), f"{path}.shape is invalid"
        for key in ("w", "h", "r"):
            if key in body:
                _require_number(body[key], f"{path}.{key}", positive=True)
        dimensions = ("r",) if shape == "circle" else ("w", "h")
        for key in dimensions:
            assert key in body, f"{path}.{key} is required for {shape}"
    assert len(ids) == len(set(ids)), "body IDs must be unique"


def _reject_nonfinite_json(token):
    raise ValueError(f"non-finite JSON number {token}")


def validate_output_record(record, expected_step, input_bodies):
    assert type(record) is dict
    assert set(record) == {"step", "bodies"}
    assert type(record["step"]) is int and record["step"] == expected_step
    assert type(record["bodies"]) is list
    expected_ids = sorted(body["id"] for body in input_bodies)
    actual_ids = []
    for index, body in enumerate(record["bodies"]):
        assert type(body) is dict
        assert set(body) == OUTPUT_BODY_KEYS, f"output body {index} does not match schema"
        assert type(body["id"]) is int
        actual_ids.append(body["id"])
        for key in STATE_KEYS:
            value = body[key]
            _require_number(value, f"step {expected_step}.bodies[{index}].{key}")
            assert value == round(value, 6), f"{key} is not rounded to six decimals"
    assert actual_ids == expected_ids


def run_sim(config: dict, steps: int, *, timeout=120):
    validate_config(config)
    assert type(steps) is int and steps >= 0
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as cf:
        json.dump(config, cf)
        cfg_path = cf.name
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as of:
        out_path = of.name
    try:
        r = subprocess.run(
            ["python3", SCRIPT, "--config", cfg_path, "--output", out_path,
             "--steps", str(steps)],
            capture_output=True, text=True, timeout=timeout,
        )
        assert r.returncode == 0, f"simulator exited {r.returncode}:\n{r.stderr}"
        lines = open(out_path, encoding="utf-8").read().splitlines()
        assert len(lines) == steps, f"expected {steps} lines, got {len(lines)}"
        records = [
            json.loads(line, parse_constant=_reject_nonfinite_json) for line in lines
        ]
        for index, record in enumerate(records):
            validate_output_record(record, index, config["bodies"])
        return records
    finally:
        os.unlink(cfg_path)
        if os.path.exists(out_path):
            os.unlink(out_path)


def approx(a, b, tol=1e-3):
    return abs(a - b) < tol


def body_cfg(id=0, x=50.0, y=50.0, vx=0.0, vy=0.0,
             angle=0.0, omega=0.0, mass=1.0, w=2.0, h=2.0,
             e=1.0, mu=0.0):
    return {"id": id, "x": x, "y": y, "vx": vx, "vy": vy,
            "angle": angle, "omega": omega, "mass": mass,
            "w": w, "h": h, "e": e, "mu": mu}


def circle_cfg(id=0, x=50.0, y=50.0, vx=0.0, vy=0.0,
               angle=0.0, omega=0.0, mass=1.0, r=2.0,
               e=1.0, mu=0.0):
    return {"id": id, "x": x, "y": y, "vx": vx, "vy": vy,
            "angle": angle, "omega": omega, "mass": mass,
            "shape": "circle", "r": r, "e": e, "mu": mu}


def cfg(bodies, width=400.0, height=400.0, dt=0.01, g=0.0,
        solver_iterations=10):
    return {"width": width, "height": height, "dt": dt, "g": g,
            "solver_iterations": solver_iterations, "bodies": bodies}


def total_momentum(step, bodies_cfg):
    """Compute total linear momentum (px, py) from a step dict."""
    mass_map = {b["id"]: b["mass"] for b in bodies_cfg}
    px = py = 0.0
    for b in step["bodies"]:
        m = mass_map[b["id"]]
        px += m * b["vx"]
        py += m * b["vy"]
    return px, py


def _body_inertia(b):
    """Compute moment of inertia for a body config dict."""
    m = b["mass"]
    if b.get("shape") == "circle":
        return 0.5 * m * b["r"]**2
    return m * (b["w"]**2 + b["h"]**2) / 12.0


def total_ke(step, bodies_cfg):
    """Compute total kinetic energy (linear + rotational)."""
    mass_map = {b["id"]: b["mass"] for b in bodies_cfg}
    inertia_map = {b["id"]: _body_inertia(b) for b in bodies_cfg}
    ke = 0.0
    for b in step["bodies"]:
        m = mass_map[b["id"]]
        I = inertia_map[b["id"]]
        ke += 0.5 * m * (b["vx"]**2 + b["vy"]**2)
        ke += 0.5 * I * b.get("omega", 0.0)**2
    return ke


def total_angular_momentum(step, bodies_cfg):
    """Total angular momentum about origin: L = sum(m*(x*vy - y*vx) + I*omega)."""
    mass_map = {b["id"]: b["mass"] for b in bodies_cfg}
    inertia_map = {b["id"]: _body_inertia(b) for b in bodies_cfg}
    L = 0.0
    for b in step["bodies"]:
        m = mass_map[b["id"]]
        I = inertia_map[b["id"]]
        L += m * (b["x"] * b["vy"] - b["y"] * b["vx"])
        L += I * b.get("omega", 0.0)
    return L


# Baseline assertions moved out of the compact public smoke suite.


def test_hidden_cli_step_counts_and_schema_baseline():
    assert os.path.isfile(SCRIPT), f"{SCRIPT} not found"
    config = cfg([body_cfg()])
    for count in (1, 10, 100):
        assert len(run_sim(config, count)) == count


def test_hidden_free_rotation_and_gravity_baseline():
    rotation = run_sim(
        cfg(
            [body_cfg(angle=0.5, omega=2.0)],
            width=1000.0,
            height=1000.0,
            dt=0.1,
        ),
        5,
    )
    for index, step in enumerate(rotation, start=1):
        state = step["bodies"][0]
        assert approx(state["angle"], 0.5 + 0.2 * index, tol=1e-4)
        assert approx(state["omega"], 2.0, tol=1e-4)

    falling = run_sim(
        cfg([body_cfg(y=100.0)], width=1000.0, height=1000.0, dt=0.1, g=9.81),
        5,
    )
    velocities = [step["bodies"][0]["vy"] for step in falling]
    assert all(current > previous for previous, current in zip([0.0] + velocities, velocities))


def test_hidden_inelastic_wall_bounce_baseline():
    steps = run_sim(
        cfg([body_cfg(x=25.0, y=50.0, vx=10.0, e=0.5)], width=30.0, height=100.0, dt=0.1),
        10,
    )
    post_bounce = next(state["bodies"][0]["vx"] for state in steps if state["bodies"][0]["vx"] < 0)
    assert 2.0 < abs(post_bounce) < 8.0


def test_hidden_resting_body_settles_baseline():
    steps = run_sim(
        cfg(
            [body_cfg(x=50.0, y=90.0, w=4.0, h=4.0, e=0.5, mu=0.1)],
            width=100.0,
            height=100.0,
            dt=0.01,
            g=9.81,
        ),
        500,
        timeout=120,
    )
    final = steps[-1]["bodies"][0]
    assert abs(final["vy"]) < 2.0
    assert 90.0 < final["y"] < 100.0


def test_hidden_body_body_separation_baseline():
    bodies = [
        body_cfg(id=0, x=95.0, y=100.0, vx=10.0, w=4.0, h=4.0),
        body_cfg(id=1, x=105.0, y=100.0, vx=-10.0, w=4.0, h=4.0),
    ]
    steps = run_sim(cfg(bodies, width=200.0, height=200.0, dt=0.05), 20)
    for step in steps[5:]:
        by_id = {body["id"]: body for body in step["bodies"]}
        assert abs(by_id[1]["x"] - by_id[0]["x"]) > 3.0


def test_hidden_circle_free_motion_and_wall_baseline():
    circle = circle_cfg(x=100.0, y=100.0, vx=5.0, vy=-2.0, r=1.0)
    free = run_sim(cfg([circle], width=400.0, height=400.0, dt=0.1), 5)
    for index, step in enumerate(free, start=1):
        state = step["bodies"][0]
        assert approx(state["x"], 100.0 + 0.5 * index, tol=1e-4)
        assert approx(state["y"], 100.0 - 0.2 * index, tol=1e-4)

    wall_circle = circle_cfg(x=95.0, y=50.0, vx=10.0, r=2.0)
    wall = run_sim(cfg([wall_circle], width=100.0, height=100.0, dt=0.1), 10)
    velocities = [step["bodies"][0]["vx"] for step in wall]
    assert any(vx < 0 for vx in velocities)
    assert all(approx(abs(vx), 10.0, tol=0.5) for vx in velocities)


def test_hidden_circle_circle_collision_baseline():
    bodies = [
        circle_cfg(id=0, x=45.0, y=100.0, vx=10.0, r=3.0),
        circle_cfg(id=1, x=55.0, y=100.0, vx=-10.0, r=3.0),
    ]
    steps = run_sim(cfg(bodies, width=200.0, height=200.0, dt=0.01), 30)
    assert any(step["bodies"][0]["vx"] < 0 for step in steps)


# ===========================================================================
# 10 HARDEST PASSING TESTS (rect-rect, solver mechanics)
# ===========================================================================


# 1. OBB: no false positive (parallel rotated bars, AABBs overlap but OBBs don't)

def test_obb_no_false_positive():
    """Two thin parallel bars at 45deg, offset perpendicular to their length.
    AABBs overlap but OBBs do NOT. Velocities must remain unchanged."""
    angle = math.pi / 4
    bodies = [
        body_cfg(id=0, x=50.0, y=47.0, vx=2.0, vy=0.0,
                 w=20.0, h=1.0, angle=angle),
        body_cfg(id=1, x=50.0, y=53.0, vx=-2.0, vy=0.0,
                 w=20.0, h=1.0, angle=angle),
    ]
    config = cfg(bodies, width=200.0, height=200.0, dt=0.01)
    steps = run_sim(config, 10)
    for i, s in enumerate(steps):
        b0 = next(b for b in s["bodies"] if b["id"] == 0)
        b1 = next(b for b in s["bodies"] if b["id"] == 1)
        assert approx(b0["vx"], 2.0, tol=0.01), \
            f"step {i}: body 0 vx changed to {b0['vx']} (false positive collision)"
        assert approx(b1["vx"], -2.0, tol=0.01), \
            f"step {i}: body 1 vx changed to {b1['vx']} (false positive collision)"


# 2. Exact off-center angular impulse

def test_exact_off_center_angular_impulse():
    """A(x=49, y=99.5, vx=10) and B(x=51, y=100.5, vx=-10), equal mass=1,
    w=h=2, e=1, mu=0. The y-offset causes angular impulse.

    After integration: A=(49.1, 99.5), B=(50.9, 100.5)
    SAT: x-overlap=0.2, y-overlap=1.0. Normal axis (1,0), depth 0.2.
    n=(-1,0) [from B toward A].
    Support A: vertices at x=50.1 -> mean (50.1, 99.5)
    Support B: vertices at x=49.9 -> mean (49.9, 100.5)
    P = (50.0, 100.0)
    rA = (0.9, 0.5), rB = (-0.9, -0.5)
    I = 1*(4+4)/12 = 2/3
    rAxN = 0.9*0 - 0.5*(-1) = 0.5
    rBxN = (-0.9)*0 - (-0.5)*(-1) = -0.5
    denom = 1+1 + 0.25/(2/3) + 0.25/(2/3) = 2 + 0.375 + 0.375 = 2.75
    jN = -(1+1)*(-20)/2.75 = 40/2.75 = 14.545454...
    vA.x = 10 - 14.545454 = -4.545454
    vB.x = -10 + 14.545454 = 4.545454
    omegaA = 0.5 * 14.545454 / (2/3) = 10.909091
    omegaB = -(-0.5) * 14.545454 / (2/3) = 10.909091
    """
    bodies = [
        body_cfg(id=0, x=49.0, y=99.5, vx=10.0, vy=0.0,
                 mass=1.0, w=2.0, h=2.0, e=1.0, mu=0.0),
        body_cfg(id=1, x=51.0, y=100.5, vx=-10.0, vy=0.0,
                 mass=1.0, w=2.0, h=2.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, width=200.0, height=200.0, dt=0.01)
    steps = run_sim(config, 1)

    b0 = next(b for b in steps[0]["bodies"] if b["id"] == 0)
    b1 = next(b for b in steps[0]["bodies"] if b["id"] == 1)

    assert approx(b0["vx"], -4.5455, tol=0.05), \
        f"body 0 vx={b0['vx']}, expected -4.5455"
    assert approx(b1["vx"], 4.5455, tol=0.05), \
        f"body 1 vx={b1['vx']}, expected 4.5455"
    assert approx(b0["omega"], 10.9091, tol=0.1), \
        f"body 0 omega={b0['omega']}, expected 10.9091"
    assert approx(b1["omega"], 10.9091, tol=0.1), \
        f"body 1 omega={b1['omega']}, expected 10.9091"


# 3. Accumulated impulse prevents energy gain

def test_exact_accumulated_clamping_behavior():
    """Without accumulated impulse clamping, repeated solver iterations would
    each apply the full impulse, causing over-correction. With clamping,
    only the DELTA is applied, preventing energy gain.

    Two bodies collide. After 1 step with solver_iterations=20, the total
    kinetic energy must NOT exceed the initial KE (for e<=1).
    """
    bodies = [
        body_cfg(id=0, x=98.0, y=200.0, vx=8.0, mass=1.0,
                 w=4.0, h=4.0, e=0.7, mu=0.0),
        body_cfg(id=1, x=102.0, y=200.0, vx=-8.0, mass=1.0,
                 w=4.0, h=4.0, e=0.7, mu=0.0),
    ]
    config = cfg(bodies, dt=0.02, solver_iterations=20)
    steps = run_sim(config, 1)

    ke_initial = 0.5 * 1.0 * 64 + 0.5 * 1.0 * 64  # 64
    ke_final = total_ke(steps[0], bodies)

    # With e=0.7, KE should decrease. With proper clamping, it must not increase.
    assert ke_final <= ke_initial * 1.01, \
        f"Energy increased: initial={ke_initial:.4f}, final={ke_final:.4f} " \
        f"(accumulated clamping may be broken)"
    assert ke_final < ke_initial * 0.8, \
        f"Not enough energy loss for e=0.7: initial={ke_initial:.4f}, final={ke_final:.4f}"


# 4. Friction bound uses accumulated normal impulse

def test_exact_friction_uses_accumulated_normal():
    """Friction bound should use the ACCUMULATED normal impulse (accN),
    not the raw per-iteration jN. With high mu and many solver iterations,
    incorrect friction bounding causes visible errors in tangential velocity."""
    bodies = [
        body_cfg(id=0, x=97.0, y=199.0, vx=8.0, vy=2.0,
                 mass=1.0, w=4.0, h=4.0, e=0.5, mu=0.8),
        body_cfg(id=1, x=103.0, y=201.0, vx=-8.0, vy=-2.0,
                 mass=1.0, w=4.0, h=4.0, e=0.5, mu=0.8),
    ]
    config = cfg(bodies, dt=0.02, solver_iterations=15)
    steps = run_sim(config, 10)

    # Verify that friction affected tangential velocity (vy should change)
    # and that the result is physically reasonable (no explosion)
    for s in steps:
        for b in s["bodies"]:
            speed = math.sqrt(b["vx"]**2 + b["vy"]**2)
            assert speed < 20.0, \
                f"Velocity explosion: body {b['id']} speed={speed:.4f}"
            assert abs(b.get("omega", 0.0)) < 100.0, \
                f"Angular velocity explosion: body {b['id']} omega={b['omega']:.4f}"

    # After collision with friction, bodies should have acquired omega
    b0_final = next(b for b in steps[-1]["bodies"] if b["id"] == 0)
    b1_final = next(b for b in steps[-1]["bodies"] if b["id"] == 1)
    assert abs(b0_final.get("omega", 0.0)) > 0.01 or abs(b1_final.get("omega", 0.0)) > 0.01, \
        "Friction with off-center contact should produce angular velocity"


# 5. Velocity threshold: exact zero-restitution at low relative speed

def test_exact_velocity_threshold_body_body():
    """Two bodies approach slowly (vx=+-0.4). After integration they overlap.
    Relative vN will be < 1.0 in magnitude, so e_combined must be 0.
    With e=0 and equal mass: both bodies stop (vx -> 0).
    With e=1 (no threshold): velocities would swap.
    """
    # Bodies close together, slow approach
    bodies = [
        body_cfg(id=0, x=99.5, y=200.0, vx=0.4, vy=0.0,
                 mass=1.0, w=2.0, h=2.0, e=0.9, mu=0.0),
        body_cfg(id=1, x=100.5, y=200.0, vx=-0.4, vy=0.0,
                 mass=1.0, w=2.0, h=2.0, e=0.9, mu=0.0),
    ]
    config = cfg(bodies, width=400.0, height=400.0, dt=0.1)
    steps = run_sim(config, 1)

    b0 = next(b for b in steps[0]["bodies"] if b["id"] == 0)
    b1 = next(b for b in steps[0]["bodies"] if b["id"] == 1)

    # With velocity threshold (|vN| < 1.0 => e=0), equal-mass inelastic:
    # both bodies should have ~0 velocity (not bounced back)
    assert abs(b0["vx"]) < 0.3, \
        f"body 0 vx={b0['vx']}, expected ~0 (velocity threshold should set e=0)"
    assert abs(b1["vx"]) < 0.3, \
        f"body 1 vx={b1['vx']}, expected ~0 (velocity threshold should set e=0)"


# 6. Three-body stacking stability

def test_stacking_stability():
    """Three bodies stacked vertically on the floor with gravity. They should
    reach a stable equilibrium without sinking through each other or the floor."""
    H = 100.0
    bodies = [
        body_cfg(id=0, x=50.0, y=H - 3.0, vx=0.0, vy=0.0,
                 mass=2.0, w=6.0, h=4.0, e=0.0, mu=0.5),
        body_cfg(id=1, x=50.0, y=H - 7.0, vx=0.0, vy=0.0,
                 mass=1.5, w=5.0, h=4.0, e=0.0, mu=0.5),
        body_cfg(id=2, x=50.0, y=H - 11.0, vx=0.0, vy=0.0,
                 mass=1.0, w=4.0, h=4.0, e=0.0, mu=0.5),
    ]
    config = cfg(bodies, width=100.0, height=H, dt=0.01, g=9.81,
                 solver_iterations=20)
    steps = run_sim(config, 500, timeout=180)

    # All bodies should remain above floor (y < H)
    for s in steps[-50:]:
        for b in s["bodies"]:
            assert b["y"] < H + 1.0, \
                f"Body {b['id']} fell through floor: y={b['y']}"

    # Bodies should be ordered by y (body 0 lowest, body 2 highest)
    for s in steps[-50:]:
        ys = {b["id"]: b["y"] for b in s["bodies"]}
        assert ys[0] > ys[1] > ys[2], \
            f"Stack collapsed: y0={ys[0]:.2f}, y1={ys[1]:.2f}, y2={ys[2]:.2f}"

    # Velocities should be small at the end (stack settled)
    for b in steps[-1]["bodies"]:
        speed = math.sqrt(b["vx"]**2 + b["vy"]**2)
        assert speed < 3.0, \
            f"Body {b['id']} not settled: speed={speed:.4f}"


# 7. Exact head-on elastic collision

def test_exact_head_on_elastic():
    """Two equal-mass bodies approach head-on with vx=10 and vx=-10.
    After 1 step (dt=0.01): they overlap, impulse reverses velocities.

    Setup: A at x=49, B at x=51, both w=2, h=2, mass=1, e=1, mu=0.
    After integration: A.x=49.1, B.x=50.9
    SAT overlap on x-axis: 0.2 (min of 0.2 and 2.0)
    Normal: (-1, 0) [from B toward A, since posA < posB]
    Contact point: (50.0, 100.0)
    rA = (0.9, 0), rB = (-0.9, 0), rAxN=0, rBxN=0
    jN = -(1+1)*(-20)/(1+1) = 20
    vA_new = 10 - 20 = -10, vB_new = -10 + 20 = 10
    Position correction: d=0.2, corr=max(0.2-0.005,0)*0.2=0.039
    A.x -= 0.0195, B.x += 0.0195
    """
    bodies = [
        body_cfg(id=0, x=49.0, y=100.0, vx=10.0, vy=0.0,
                 mass=1.0, w=2.0, h=2.0, e=1.0, mu=0.0),
        body_cfg(id=1, x=51.0, y=100.0, vx=-10.0, vy=0.0,
                 mass=1.0, w=2.0, h=2.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, width=200.0, height=200.0, dt=0.01)
    steps = run_sim(config, 1)

    b0 = next(b for b in steps[0]["bodies"] if b["id"] == 0)
    b1 = next(b for b in steps[0]["bodies"] if b["id"] == 1)

    # Velocities should swap (elastic equal-mass)
    assert approx(b0["vx"], -10.0, tol=0.01), \
        f"body 0 vx={b0['vx']}, expected -10.0"
    assert approx(b1["vx"], 10.0, tol=0.01), \
        f"body 1 vx={b1['vx']}, expected 10.0"
    # Position correction applied
    assert approx(b0["x"], 49.0805, tol=0.01), \
        f"body 0 x={b0['x']}, expected ~49.0805 (with position correction)"
    assert approx(b1["x"], 50.9195, tol=0.01), \
        f"body 1 x={b1['x']}, expected ~50.9195 (with position correction)"
    # No angular velocity should be generated (symmetric)
    assert approx(b0["omega"], 0.0, tol=1e-4), \
        f"body 0 omega={b0['omega']}, expected 0"
    assert approx(b1["omega"], 0.0, tol=1e-4), \
        f"body 1 omega={b1['omega']}, expected 0"


# 8. Exact unequal-mass collision with COR

def test_exact_unequal_mass_cor():
    """A(mass=2, vx=10) hits B(mass=1, vx=-5), both e=0.8, mu=0.
    After integration: A.x=49.1, B.x=50.95.
    Overlap=0.15. Normal=(-1,0). rAxN=rBxN=0.
    e_combined = sqrt(0.8*0.8) = 0.8, |vN|=15>=1.
    jN = -(1+0.8)*(-15)/(0.5+1) = 27/1.5 = 18
    vA = 10 - 18/2 = 1.0,  vB = -5 + 18/1 = 13.0
    Position corr: d=0.15, corr=max(0.145,0)*0.2=0.029
    totalInvMass=1.5. A.x -= (0.5/1.5)*0.029 ~ 49.09033
    B.x += (1.0/1.5)*0.029 ~ 50.96933
    """
    bodies = [
        body_cfg(id=0, x=49.0, y=100.0, vx=10.0, vy=0.0,
                 mass=2.0, w=2.0, h=2.0, e=0.8, mu=0.0),
        body_cfg(id=1, x=51.0, y=100.0, vx=-5.0, vy=0.0,
                 mass=1.0, w=2.0, h=2.0, e=0.8, mu=0.0),
    ]
    config = cfg(bodies, width=200.0, height=200.0, dt=0.01)
    steps = run_sim(config, 1)

    b0 = next(b for b in steps[0]["bodies"] if b["id"] == 0)
    b1 = next(b for b in steps[0]["bodies"] if b["id"] == 1)

    # Check momentum conservation: 2*10 + 1*(-5) = 15 = 2*1 + 1*13
    assert approx(b0["vx"], 1.0, tol=0.05), \
        f"body 0 vx={b0['vx']}, expected 1.0"
    assert approx(b1["vx"], 13.0, tol=0.05), \
        f"body 1 vx={b1['vx']}, expected 13.0"
    # Position correction
    assert approx(b0["x"], 49.0903, tol=0.01), \
        f"body 0 x={b0['x']}, expected ~49.0903"
    assert approx(b1["x"], 50.9693, tol=0.01), \
        f"body 1 x={b1['x']}, expected ~50.9693"


# 9. Wall gentle contact: velocity threshold kills bounce

def test_wall_gentle_contact_no_bounce():
    """Body approaches wall very slowly (vx=0.5). With velocity-dependent
    restitution (|vN| < 1.0 => e=0), it should NOT bounce back.
    Instead it should stop or continue at near-zero velocity."""
    bodies = [
        body_cfg(id=0, x=198.0, y=100.0, vx=0.5, vy=0.0,
                 mass=1.0, w=2.0, h=2.0, e=0.9, mu=0.0),
    ]
    config = cfg(bodies, width=200.0, height=200.0, dt=0.01)
    steps = run_sim(config, 100)

    # After hitting wall gently, body should NOT bounce back significantly
    # (e should be treated as 0 due to velocity threshold)
    bounced = False
    for s in steps[20:]:
        if s["bodies"][0]["vx"] < -0.3:
            bounced = True
            break

    assert not bounced, \
        "Body bounced back from gentle wall contact (velocity threshold not applied)"


# 10. Wall friction induces angular velocity

def test_exact_wall_friction_spin():
    """Body sliding right along bottom wall with mu=1.0 and initial vy=5.
    After integration, bottom vertex penetrates floor.
    Floor normal n=(0,-1). Contact at bottom vertex.
    After normal impulse kills vy, friction applies tangential impulse
    to slow vx and induce omega.

    Friction at bottom contact: body slides right, friction pushes left,
    r points down from center. Torque = r x F produces positive omega (CCW).
    This is consistent with the body starting to "roll" rightward.
    """
    bodies = [
        body_cfg(id=0, x=50.0, y=99.0, vx=10.0, vy=5.0,
                 mass=1.0, w=2.0, h=2.0, e=0.0, mu=1.0),
    ]
    config = cfg(bodies, width=200.0, height=100.0, dt=0.01, g=9.81)
    steps = run_sim(config, 5)

    # After floor contact, omega should become positive (CCW in y-down coords)
    # because friction at the bottom pushes the contact point backward,
    # creating a torque that spins the body in the rolling direction.
    found_spin = False
    for s in steps:
        omega = s["bodies"][0]["omega"]
        if abs(omega) > 0.1:
            assert omega > 0, \
                f"omega={omega}, expected positive (friction-induced roll)"
            found_spin = True
            break

    assert found_spin, "Wall friction didn't induce angular velocity"


# ===========================================================================
# 20 GPT-5 FAILURES (circle-rect and advanced scenarios)
# ===========================================================================


# 11. Wall processing order: corner scenario

def test_exact_wall_order_corner():
    """Body heading toward bottom-right corner with g=0. Spec says wall order
    is left, right, top, bottom. Both walls hit simultaneously in step 2."""
    W, H = 50.0, 50.0
    bodies = [
        body_cfg(id=0, x=48.0, y=48.0, vx=10.0, vy=10.0,
                 mass=1.0, w=2.0, h=2.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, width=W, height=H, dt=0.1, g=0.0)
    steps = run_sim(config, 3)

    # Step 1: x=49, y=49 -- vertices at (50,48),(48,48),(48,50),(50,50)
    #   Right wall: pen=0, bottom wall: pen=0 -> no wall hit
    # Step 2: x=50, y=50 -- vertices at (51,49),(49,49),(49,51),(51,51)
    #   Right wall: pen=1 (v0,v3), bottom wall: pen=1 (v2,v3)
    #   Both walls hit, both velocities should reverse
    b = steps[1]["bodies"][0]
    assert b["vx"] < 0, \
        f"vx={b['vx']}, expected negative (bounced off right wall)"
    assert b["vy"] < 0, \
        f"vy={b['vy']}, expected negative (bounced off bottom wall)"


# 12. Circle bounces off stationary rect head-on

def test_circle_rect_head_on():
    """Circle approaches stationary rect head-on.
    After elastic collision, circle should bounce back."""
    bodies = [
        circle_cfg(id=0, x=42.0, y=200.0, vx=8.0,
                   mass=1.0, r=3.0, e=1.0, mu=0.0),
        body_cfg(id=1, x=55.0, y=200.0, vx=0.0,
                 mass=1.0, w=6.0, h=6.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 50)

    # Circle should bounce back
    found_bounce = False
    for s in steps[5:]:
        b0 = next(b for b in s["bodies"] if b["id"] == 0)
        if b0["vx"] < -1.0:
            found_bounce = True
            break

    assert found_bounce, "Circle didn't bounce off rectangle"

    # Rect should start moving right
    found_rect_move = False
    for s in steps[5:]:
        b1 = next(b for b in s["bodies"] if b["id"] == 1)
        if b1["vx"] > 1.0:
            found_rect_move = True
            break

    assert found_rect_move, "Rectangle didn't move after circle collision"


# 13. Circle vs rect rotated at pi/4

def test_circle_rect_rotated():
    """Circle collides with a rotated rectangle (angle=pi/4).
    The collision normal should account for the rect's rotation."""
    import math as m
    bodies = [
        circle_cfg(id=0, x=42.0, y=200.0, vx=10.0,
                   mass=1.0, r=2.0, e=1.0, mu=0.0),
        body_cfg(id=1, x=55.0, y=200.0, vx=0.0, angle=m.pi/4,
                 mass=2.0, w=8.0, h=2.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 80)

    # After collision with rotated rect, circle should change direction
    b0_initial_vx = 10.0
    found_change = False
    for s in steps[10:]:
        b0 = next(b for b in s["bodies"] if b["id"] == 0)
        if abs(b0["vx"] - b0_initial_vx) > 2.0:
            found_change = True
            break

    assert found_change, "Circle didn't respond to rotated rect collision"


# 14. Circle falls onto top of rect

def test_circle_rect_vertical_bounce():
    """Circle falling onto top of stationary rect. Should bounce upward."""
    bodies = [
        circle_cfg(id=0, x=100.0, y=185.0, vx=0.0, vy=10.0,
                   mass=1.0, r=3.0, e=1.0, mu=0.0),
        body_cfg(id=1, x=100.0, y=200.0, vx=0.0,
                 mass=100.0, w=20.0, h=6.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 50)

    # Circle should bounce back (vy goes negative)
    found_bounce = False
    for s in steps[5:]:
        b0 = next(b for b in s["bodies"] if b["id"] == 0)
        if b0["vy"] < -1.0:
            found_bounce = True
            break
    assert found_bounce, "Circle didn't bounce off top of rect"


# 15. Circle hits rect from the left

def test_circle_rect_side_approach():
    """Circle approaching rect from the left. Should bounce back on x-axis."""
    bodies = [
        circle_cfg(id=0, x=80.0, y=200.0, vx=15.0,
                   mass=1.0, r=3.0, e=1.0, mu=0.0),
        body_cfg(id=1, x=100.0, y=200.0, vx=0.0,
                 mass=100.0, w=10.0, h=10.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 50)

    found_bounce = False
    for s in steps[5:]:
        b0 = next(b for b in s["bodies"] if b["id"] == 0)
        if b0["vx"] < -1.0:
            found_bounce = True
            break
    assert found_bounce, "Circle didn't bounce off left side of rect"


# 16. Circle aimed at rect corner, deflected

def test_circle_rect_corner_collision():
    """Circle aimed at corner of rect. Should be deflected."""
    bodies = [
        circle_cfg(id=0, x=85.0, y=190.0, vx=10.0, vy=5.0,
                   mass=1.0, r=2.0, e=1.0, mu=0.0),
        body_cfg(id=1, x=100.0, y=200.0, vx=0.0,
                 mass=100.0, w=10.0, h=10.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 40)

    # After hitting corner, circle should change direction
    initial_vx = 10.0
    found_deflection = False
    for s in steps[5:]:
        b0 = next(b for b in s["bodies"] if b["id"] == 0)
        if b0["vx"] < initial_vx * 0.5:
            found_deflection = True
            break
    assert found_deflection, "Circle not deflected by rect corner"


# 17. Circle hits rect from below

def test_circle_rect_bottom_approach():
    """Circle moving upward into bottom of rect. Should bounce down."""
    bodies = [
        circle_cfg(id=0, x=100.0, y=215.0, vx=0.0, vy=-10.0,
                   mass=1.0, r=3.0, e=1.0, mu=0.0),
        body_cfg(id=1, x=100.0, y=200.0, vx=0.0,
                 mass=100.0, w=20.0, h=6.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 50)

    found_bounce = False
    for s in steps[5:]:
        b0 = next(b for b in s["bodies"] if b["id"] == 0)
        if b0["vy"] > 1.0:
            found_bounce = True
            break
    assert found_bounce, "Circle didn't bounce off bottom of rect"


# 18. Small circle vs wide thin rect

def test_circle_small_vs_wide_rect():
    """Small circle hitting a very wide, thin rect. Collision normal
    should point upward (away from top face)."""
    bodies = [
        circle_cfg(id=0, x=100.0, y=192.0, vx=0.0, vy=8.0,
                   mass=1.0, r=1.0, e=1.0, mu=0.0),
        body_cfg(id=1, x=100.0, y=200.0, vx=0.0,
                 mass=50.0, w=40.0, h=2.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 30)

    found_bounce = False
    for s in steps[5:]:
        b0 = next(b for b in s["bodies"] if b["id"] == 0)
        if b0["vy"] < -1.0:
            found_bounce = True
            break
    assert found_bounce, "Small circle didn't bounce off wide rect"


# 19. Circle vs 45-degree rotated rect

def test_circle_rect_45deg():
    """Circle approaches a rect rotated 45 degrees. This is a harder
    collision detection case (diamond shape in world coords)."""
    bodies = [
        circle_cfg(id=0, x=85.0, y=200.0, vx=10.0,
                   mass=1.0, r=3.0, e=1.0, mu=0.0),
        body_cfg(id=1, x=100.0, y=200.0, vx=0.0, angle=math.pi/4,
                 mass=100.0, w=8.0, h=8.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 40)

    found_bounce = False
    for s in steps[5:]:
        b0 = next(b for b in s["bodies"] if b["id"] == 0)
        if b0["vx"] < 0.0:
            found_bounce = True
            break
    assert found_bounce, "Circle didn't bounce off 45-degree rotated rect"


# 20. Equal-mass elastic circle-rect velocity transfer

def test_circle_rect_equal_mass_exchange():
    """Equal mass circle and rect, head-on elastic collision.
    Velocities should approximately swap (like 1D elastic)."""
    bodies = [
        circle_cfg(id=0, x=140.0, y=200.0, vx=10.0,
                   mass=2.0, r=3.0, e=1.0, mu=0.0),
        body_cfg(id=1, x=160.0, y=200.0, vx=0.0,
                 mass=2.0, w=6.0, h=6.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 60)

    # After elastic head-on, circle should slow/stop, rect should gain speed
    b0_last = steps[-1]["bodies"][0]
    b1_last = steps[-1]["bodies"][1]
    # Circle should have lost most of its vx
    assert b0_last["vx"] < 5.0, \
        f"Circle didn't transfer momentum to rect: circle vx={b0_last['vx']:.4f}"
    # Rect should have gained vx
    assert b1_last["vx"] > 2.0, \
        f"Rect didn't gain momentum from circle: rect vx={b1_last['vx']:.4f}"


# 21. Circle-circle with mu=0.3 produces friction spin

def test_circle_circle_tangential_spin():
    """Two circles with slight vertical offset collide.
    Off-center contact should produce angular velocity in both."""
    bodies = [
        circle_cfg(id=0, x=140.0, y=198.0, vx=10.0,
                   mass=1.0, r=4.0, e=1.0, mu=0.3),
        circle_cfg(id=1, x=155.0, y=202.0, vx=-5.0,
                   mass=1.0, r=4.0, e=1.0, mu=0.3),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 50)

    omega0 = max(abs(s["bodies"][0].get("omega", 0.0)) for s in steps)
    omega1 = max(abs(s["bodies"][1].get("omega", 0.0)) for s in steps)
    assert omega0 > 0.05 or omega1 > 0.05, \
        f"Tangential circle collision produced no spin: omega0={omega0:.4f}, omega1={omega1:.4f}"


# 22. Two circle-rect pairs collide simultaneously

def test_multiple_circle_rect_pairs():
    """Two circle-rect pairs colliding simultaneously.
    Tests that the solver handles mixed body types in the same iteration."""
    bodies = [
        circle_cfg(id=0, x=85.0, y=100.0, vx=10.0,
                   mass=1.0, r=3.0, e=0.8, mu=0.0),
        body_cfg(id=1, x=100.0, y=100.0, vx=0.0,
                 mass=2.0, w=6.0, h=6.0, e=0.8, mu=0.0),
        circle_cfg(id=2, x=85.0, y=200.0, vx=12.0,
                   mass=1.5, r=4.0, e=0.8, mu=0.0),
        body_cfg(id=3, x=100.0, y=200.0, vx=0.0,
                 mass=2.5, w=8.0, h=8.0, e=0.8, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 60)

    # Both circles should bounce
    bounced_0 = any(s["bodies"][0]["vx"] < 0 for s in steps[10:])
    bounced_2 = any(s["bodies"][2]["vx"] < 0 for s in steps[10:])
    assert bounced_0, "Circle 0 didn't bounce off rect 1"
    assert bounced_2, "Circle 2 didn't bounce off rect 3"


# 23. Moving rect hits stationary circle

def test_circle_rect_moving_rect():
    """Stationary circle hit by moving rect. Circle should acquire velocity."""
    bodies = [
        circle_cfg(id=0, x=100.0, y=200.0, vx=0.0,
                   mass=1.0, r=3.0, e=1.0, mu=0.0),
        body_cfg(id=1, x=80.0, y=200.0, vx=10.0,
                 mass=1.0, w=6.0, h=6.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 60)

    # Circle should gain positive vx from rect
    found_motion = False
    for s in steps[10:]:
        b0 = next(b for b in s["bodies"] if b["id"] == 0)
        if b0["vx"] > 2.0:
            found_motion = True
            break
    assert found_motion, "Stationary circle wasn't pushed by moving rect"


# 24. Heavy circle barely slows, light rect flies

def test_circle_heavy_vs_light_rect():
    """Heavy circle hits light rect. Rect should fly away fast,
    circle barely slows."""
    bodies = [
        circle_cfg(id=0, x=140.0, y=200.0, vx=5.0,
                   mass=10.0, r=5.0, e=1.0, mu=0.0),
        body_cfg(id=1, x=160.0, y=200.0, vx=0.0,
                 mass=0.5, w=4.0, h=4.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 50)

    b0 = steps[-1]["bodies"][0]
    b1 = steps[-1]["bodies"][1]
    # Heavy circle barely slowed
    assert b0["vx"] > 3.0, \
        f"Heavy circle slowed too much: vx={b0['vx']:.4f}"
    # Light rect launched fast
    assert b1["vx"] > 5.0, \
        f"Light rect didn't fly away fast enough: vx={b1['vx']:.4f}"


# 25. Circle-rect COR=0.3 energy loss

def test_circle_rect_inelastic():
    """Circle-rect collision with e=0.3. Energy should be lost."""
    bodies = [
        circle_cfg(id=0, x=140.0, y=200.0, vx=10.0,
                   mass=1.0, r=3.0, e=0.3, mu=0.0),
        body_cfg(id=1, x=160.0, y=200.0, vx=-5.0,
                 mass=1.0, w=6.0, h=6.0, e=0.3, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 80)

    ke0 = total_ke(steps[0], bodies)
    ke_final = total_ke(steps[-1], bodies)
    assert ke_final < ke0 * 0.5, \
        f"Circle-rect inelastic didn't lose enough energy: initial={ke0:.4f}, final={ke_final:.4f}"


# 26. Friction spin from circle-rect contact (mu=0.5)

def test_circle_rect_contact_surface():
    """Circle hits rect with friction. Friction torque should produce spin,
    confirming the contact point is on the circle surface (not at center)."""
    bodies = [
        circle_cfg(id=0, x=85.0, y=199.0, vx=12.0, vy=0.0,
                   mass=1.0, r=3.0, e=0.0, mu=0.5),
        body_cfg(id=1, x=100.0, y=200.0, vx=0.0,
                 mass=100.0, w=20.0, h=4.0, e=0.0, mu=0.5),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 50)

    # Friction at contact point (circle surface) produces torque -> spin
    max_omega = max(abs(s["bodies"][0].get("omega", 0.0)) for s in steps)
    assert max_omega > 0.5, \
        f"No spin from friction: contact point may not be on circle surface. omega={max_omega:.4f}"


# 27. Circle vs 30-degree rotated rect

def test_circle_rect_30deg():
    """Circle hits rect rotated 30 degrees."""
    bodies = [
        circle_cfg(id=0, x=82.0, y=200.0, vx=10.0,
                   mass=1.0, r=3.0, e=1.0, mu=0.0),
        body_cfg(id=1, x=100.0, y=200.0, vx=0.0, angle=math.pi/6,
                 mass=100.0, w=10.0, h=6.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 40)

    # Circle should be deflected (vx decreases or reverses)
    found = False
    for s in steps[5:]:
        b0 = next(b for b in s["bodies"] if b["id"] == 0)
        if b0["vx"] < 5.0:
            found = True
            break
    assert found, "Circle didn't respond to 30-degree rotated rect"


# 28. Circle vs 90-degree rotated rect

def test_circle_rect_90deg():
    """Circle hits rect rotated 90 degrees. Should behave like hitting
    a rect with swapped width and height."""
    bodies = [
        circle_cfg(id=0, x=82.0, y=200.0, vx=10.0,
                   mass=1.0, r=3.0, e=1.0, mu=0.0),
        body_cfg(id=1, x=100.0, y=200.0, vx=0.0, angle=math.pi/2,
                 mass=100.0, w=4.0, h=12.0, e=1.0, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 40)

    found_bounce = False
    for s in steps[5:]:
        b0 = next(b for b in s["bodies"] if b["id"] == 0)
        if b0["vx"] < 0.0:
            found_bounce = True
            break
    assert found_bounce, "Circle didn't bounce off 90-degree rotated rect"


# 29. Spinning rect deflects circle vertically

def test_circle_hits_spinning_rect():
    """Circle hits a rect that has angular velocity.
    The spinning rect surface has tangential velocity at contact."""
    bodies = [
        circle_cfg(id=0, x=82.0, y=200.0, vx=10.0,
                   mass=1.0, r=3.0, e=0.8, mu=0.0),
        body_cfg(id=1, x=100.0, y=200.0, vx=0.0, omega=5.0,
                 mass=10.0, w=8.0, h=8.0, e=0.8, mu=0.0),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 40)

    # Circle should gain vertical velocity from spinning rect
    found_deflection = False
    for s in steps[5:]:
        b0 = next(b for b in s["bodies"] if b["id"] == 0)
        if abs(b0["vy"]) > 1.0:
            found_deflection = True
            break
    assert found_deflection, "Circle not deflected by spinning rect's tangential velocity"


# 30. Oblique circle-rect with mu=0.4 produces spin

def test_circle_rect_oblique_friction_spin():
    """Circle hits rect at an angle with friction.
    Friction at the circle-rect contact should induce rotation."""
    bodies = [
        circle_cfg(id=0, x=85.0, y=195.0, vx=10.0, vy=3.0,
                   mass=1.0, r=3.0, e=0.5, mu=0.4),
        body_cfg(id=1, x=100.0, y=200.0, vx=0.0,
                 mass=50.0, w=10.0, h=6.0, e=0.5, mu=0.4),
    ]
    config = cfg(bodies, dt=0.01)
    steps = run_sim(config, 60)

    max_omega = max(abs(s["bodies"][0].get("omega", 0.0)) for s in steps)
    assert max_omega > 0.1, \
        f"Circle-rect oblique friction didn't produce spin: omega={max_omega:.4f}"


# Deterministic metamorphic coverage


def test_body_input_permutation_invariance():
    bodies = [
        body_cfg(id=2, x=180.0, y=240.0, vx=0.0, w=3.0, h=5.0),
        body_cfg(id=0, x=99.0, y=200.0, vx=10.0, w=2.0, h=2.0),
        body_cfg(id=1, x=101.0, y=200.0, vx=-10.0, w=2.0, h=2.0),
    ]
    forward = run_sim(cfg(bodies, dt=0.01), 5)
    reversed_input = run_sim(cfg(list(reversed(bodies)), dt=0.01), 5)
    assert forward == reversed_input, (
        "simulation depends on config body order instead of ascending body IDs"
    )


def test_global_translation_invariance_away_from_walls():
    bodies = [
        body_cfg(id=0, x=99.0, y=199.5, vx=10.0, w=2.0, h=2.0),
        body_cfg(id=1, x=101.0, y=200.5, vx=-10.0, w=2.0, h=2.0),
    ]
    dx, dy = 37.0, 29.0
    translated = [dict(body, x=body["x"] + dx, y=body["y"] + dy) for body in bodies]
    original_step = run_sim(cfg(bodies, width=500.0, height=500.0), 1)[0]
    translated_step = run_sim(
        cfg(translated, width=500.0 + dx, height=500.0 + dy), 1
    )[0]

    original_by_id = {body["id"]: body for body in original_step["bodies"]}
    translated_by_id = {body["id"]: body for body in translated_step["bodies"]}
    for body_id, original in original_by_id.items():
        shifted = translated_by_id[body_id]
        assert approx(shifted["x"] - original["x"], dx, tol=2e-5)
        assert approx(shifted["y"] - original["y"], dy, tol=2e-5)
        for key in ("vx", "vy", "angle", "omega"):
            assert approx(shifted[key], original[key], tol=2e-5), (
                f"body {body_id} {key} changed under global translation"
            )


def _rotate_xy(x, y, angle, origin=(250.0, 250.0)):
    dx, dy = x - origin[0], y - origin[1]
    c, s = math.cos(angle), math.sin(angle)
    return origin[0] + c * dx - s * dy, origin[1] + s * dx + c * dy


def _rotate_vector(x, y, angle):
    c, s = math.cos(angle), math.sin(angle)
    return c * x - s * y, s * x + c * y


def _rotate_body(body, angle):
    x, y = _rotate_xy(body["x"], body["y"], angle)
    vx, vy = _rotate_vector(body["vx"], body["vy"], angle)
    return dict(
        body,
        x=x,
        y=y,
        vx=vx,
        vy=vy,
        angle=body.get("angle", 0.0) + angle,
    )


@pytest.mark.parametrize("rotation", [math.pi / 9, math.pi / 4, math.pi / 2])
def test_generated_obb_global_rotation_invariance(rotation):
    bodies = [
        body_cfg(id=0, x=249.0, y=249.5, vx=10.0, w=2.0, h=2.0),
        body_cfg(id=1, x=251.0, y=250.5, vx=-10.0, w=2.0, h=2.0),
    ]
    original = run_sim(cfg(bodies, width=500.0, height=500.0), 1)[0]
    rotated = run_sim(
        cfg([_rotate_body(body, rotation) for body in bodies], width=500.0, height=500.0),
        1,
    )[0]
    original_by_id = {body["id"]: body for body in original["bodies"]}
    rotated_by_id = {body["id"]: body for body in rotated["bodies"]}
    for body_id, body in original_by_id.items():
        transformed = rotated_by_id[body_id]
        expected_x, expected_y = _rotate_xy(body["x"], body["y"], rotation)
        expected_vx, expected_vy = _rotate_vector(body["vx"], body["vy"], rotation)
        assert approx(transformed["x"], expected_x, tol=3e-4)
        assert approx(transformed["y"], expected_y, tol=3e-4)
        assert approx(transformed["vx"], expected_vx, tol=3e-4)
        assert approx(transformed["vy"], expected_vy, tol=3e-4)
        assert approx(transformed["angle"], body["angle"] + rotation, tol=3e-4)
        assert approx(transformed["omega"], body["omega"], tol=3e-4)


@pytest.mark.parametrize("rotation", [0.0, math.pi / 6, math.pi / 3, math.pi / 2])
def test_generated_circle_rect_rotations(rotation):
    base = [
        circle_cfg(id=0, x=245.0, y=250.0, vx=10.0, mass=1.0, r=2.0),
        body_cfg(id=1, x=250.0, y=250.0, mass=2.0, w=4.0, h=6.0),
    ]
    bodies = [_rotate_body(body, rotation) for body in base]
    steps = run_sim(cfg(bodies, width=500.0, height=500.0, dt=0.1), 2)
    initial_vx, initial_vy = bodies[0]["vx"], bodies[0]["vy"]
    circle = next(body for body in steps[-1]["bodies"] if body["id"] == 0)
    delta = math.hypot(circle["vx"] - initial_vx, circle["vy"] - initial_vy)
    assert delta > 1.0, f"circle ignored rectangle rotated by {rotation}"


def test_generated_grazing_contact_has_no_false_impulse():
    bodies = [
        circle_cfg(id=0, x=220.0, y=246.0, vx=20.0, r=2.0),
        body_cfg(id=1, x=250.0, y=250.0, w=20.0, h=4.0),
    ]
    steps = run_sim(cfg(bodies, width=500.0, height=500.0, dt=0.05), 40)
    for step in steps:
        circle = next(body for body in step["bodies"] if body["id"] == 0)
        rect = next(body for body in step["bodies"] if body["id"] == 1)
        assert approx(circle["vx"], 20.0, tol=1e-5)
        assert approx(circle["vy"], 0.0, tol=1e-5)
        assert approx(rect["vx"], 0.0, tol=1e-5)
        assert approx(rect["vy"], 0.0, tol=1e-5)


def test_generated_high_speed_endpoint_impact_is_finite_and_conservative():
    bodies = [
        circle_cfg(id=0, x=90.0, y=200.0, vx=200.0, mass=1.5, r=3.0),
        circle_cfg(id=1, x=110.0, y=200.0, vx=-200.0, mass=1.5, r=3.0),
    ]
    steps = run_sim(cfg(bodies, dt=0.04), 5)
    first = steps[0]
    by_id = {body["id"]: body for body in first["bodies"]}
    assert by_id[0]["vx"] < 0 and by_id[1]["vx"] > 0
    px, py = total_momentum(first, bodies)
    assert approx(px, 0.0, tol=1e-4) and approx(py, 0.0, tol=1e-4)
    for step in steps:
        for body in step["bodies"]:
            assert all(math.isfinite(body[key]) for key in STATE_KEYS)


def test_generated_timestep_refinement_reduces_freefall_position_error():
    duration = 1.0

    def final_y(dt):
        steps = round(duration / dt)
        config = cfg(
            [circle_cfg(id=0, x=200.0, y=100.0, r=1.0)],
            width=1000.0,
            height=1000.0,
            dt=dt,
            g=9.81,
        )
        return run_sim(config, steps)[-1]["bodies"][0]

    coarse = final_y(0.04)
    fine = final_y(0.02)
    analytic_y = 100.0 + 0.5 * 9.81 * duration**2
    assert abs(fine["y"] - analytic_y) < abs(coarse["y"] - analytic_y)
    assert approx(fine["vy"], coarse["vy"], tol=2e-5)


def _rect_vertices_from_state(state, original):
    c, s = math.cos(state["angle"]), math.sin(state["angle"])
    hw, hh = original["w"] / 2.0, original["h"] / 2.0
    return [
        (state["x"] + sx * hw * c - sy * hh * s,
         state["y"] + sx * hw * s + sy * hh * c)
        for sx, sy in ((1, -1), (-1, -1), (-1, 1), (1, 1))
    ]


def _pair_penetration(step, originals):
    states = {body["id"]: body for body in step["bodies"]}
    first, second = originals
    a, b = states[first["id"]], states[second["id"]]
    if first.get("shape") == second.get("shape") == "circle":
        distance = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
        return max(0.0, first["r"] + second["r"] - distance)

    vertices_a = _rect_vertices_from_state(a, first)
    vertices_b = _rect_vertices_from_state(b, second)
    axes = []
    for state in (a, b):
        axes.extend(
            [(math.cos(state["angle"]), math.sin(state["angle"])),
             (-math.sin(state["angle"]), math.cos(state["angle"]))]
        )
    overlaps = []
    for axis in axes:
        projections_a = [x * axis[0] + y * axis[1] for x, y in vertices_a]
        projections_b = [x * axis[0] + y * axis[1] for x, y in vertices_b]
        overlaps.append(
            min(max(projections_a), max(projections_b))
            - max(min(projections_a), min(projections_b))
        )
    return max(0.0, min(overlaps))


@pytest.mark.parametrize("shape", ["rect", "circle"])
def test_generated_position_correction_never_increases_penetration(shape):
    if shape == "rect":
        bodies = [
            body_cfg(id=0, x=199.0, y=200.0, angle=math.pi / 7, w=4.0, h=4.0, e=0.0),
            body_cfg(id=1, x=201.0, y=200.0, angle=math.pi / 7, w=4.0, h=4.0, e=0.0),
        ]
    else:
        bodies = [
            circle_cfg(id=0, x=199.0, y=200.0, r=3.0, e=0.0),
            circle_cfg(id=1, x=202.0, y=200.0, r=3.0, e=0.0),
        ]
    steps = run_sim(cfg(bodies, dt=0.01), 12)
    penetrations = [_pair_penetration(step, bodies) for step in steps]
    assert all(
        current <= previous + 2e-5
        for previous, current in zip(penetrations, penetrations[1:])
    ), f"penetration increased: {penetrations}"
    assert penetrations[-1] < penetrations[0]
