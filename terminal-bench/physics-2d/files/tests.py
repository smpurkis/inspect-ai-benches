"""Visible tests for physics-2d: 2D rigid body physics engine.

The agent must implement /app/files/physics2d.py that accepts:
    python3 /app/files/physics2d.py --config <config.json> --output <output.jsonl> --steps <N>
"""

import json
import subprocess
import os
import tempfile
import math
import pytest

SCRIPT = "/app/files/physics2d.py"


def run_sim(config: dict, steps: int, *, timeout=60):
    """Run the physics simulator and return a list of step dicts."""
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
        lines = open(out_path).read().splitlines()
        assert len(lines) == steps, f"expected {steps} output lines, got {len(lines)}"
        return [json.loads(l) for l in lines]
    finally:
        os.unlink(cfg_path)
        if os.path.exists(out_path):
            os.unlink(out_path)


def approx(a, b, tol=1e-4):
    return abs(a - b) < tol


def simple_body(id=0, x=50.0, y=50.0, vx=0.0, vy=0.0,
                angle=0.0, omega=0.0, mass=1.0, w=2.0, h=2.0,
                e=1.0, mu=0.0):
    return {"id": id, "x": x, "y": y, "vx": vx, "vy": vy,
            "angle": angle, "omega": omega, "mass": mass,
            "w": w, "h": h, "e": e, "mu": mu}


def simple_config(bodies, width=200.0, height=200.0, dt=0.01, g=0.0,
                  solver_iterations=10):
    return {"width": width, "height": height, "dt": dt, "g": g,
            "solver_iterations": solver_iterations,
            "bodies": bodies}


# ---------------------------------------------------------------------------
# 1. Script exists
# ---------------------------------------------------------------------------

def test_script_exists():
    assert os.path.isfile(SCRIPT), f"{SCRIPT} not found"


# ---------------------------------------------------------------------------
# 2. Runs without error
# ---------------------------------------------------------------------------

def test_runs_without_error():
    cfg = simple_config([simple_body()])
    steps = run_sim(cfg, 5)
    assert len(steps) == 5


# ---------------------------------------------------------------------------
# 3. Output format: all required keys
# ---------------------------------------------------------------------------

def test_output_format():
    cfg = simple_config([simple_body(vx=1.0)])
    steps = run_sim(cfg, 3)
    for i, s in enumerate(steps):
        assert "step" in s, f"step {i}: missing 'step' key"
        assert s["step"] == i, f"step {i}: step number wrong"
        assert "bodies" in s, f"step {i}: missing 'bodies' key"
        for b in s["bodies"]:
            for key in ("id", "x", "y", "vx", "vy", "angle", "omega"):
                assert key in b, f"step {i}: body missing key '{key}'"


# ---------------------------------------------------------------------------
# 4. Bodies sorted by id
# ---------------------------------------------------------------------------

def test_bodies_sorted_by_id():
    cfg = simple_config([
        simple_body(id=2, x=150.0),
        simple_body(id=0, x=10.0),
        simple_body(id=1, x=80.0),
    ])
    steps = run_sim(cfg, 3)
    for s in steps:
        ids = [b["id"] for b in s["bodies"]]
        assert ids == sorted(ids), f"bodies not sorted by id: {ids}"


# ---------------------------------------------------------------------------
# 5. Float precision (6 decimal places)
# ---------------------------------------------------------------------------

def test_float_precision():
    cfg = simple_config([simple_body(vx=1.0)])
    steps = run_sim(cfg, 1)
    for s in steps:
        for b in s["bodies"]:
            for key in ("x", "y", "vx", "vy", "angle", "omega"):
                val = b[key]
                assert isinstance(val, (int, float)), f"{key} not a number"
                formatted = f"{val:.6f}"
                assert abs(float(formatted) - val) < 1e-9, \
                    f"{key}={val} not rounded to 6dp"


# ---------------------------------------------------------------------------
# 6. Free linear motion (no gravity, no collision)
# ---------------------------------------------------------------------------

def test_free_linear_motion():
    """Body at vx=5, vy=-3, no gravity. Check x and y trajectory."""
    cfg = simple_config([simple_body(x=100.0, y=100.0, vx=5.0, vy=-3.0)],
                        width=1000.0, height=1000.0, dt=0.1)
    steps = run_sim(cfg, 5)
    for i, s in enumerate(steps):
        b = s["bodies"][0]
        expected_x = round(100.0 + 5.0 * 0.1 * (i + 1), 6)
        expected_y = round(100.0 + (-3.0) * 0.1 * (i + 1), 6)
        assert approx(b["x"], expected_x), \
            f"step {i}: x={b['x']} expected {expected_x}"
        assert approx(b["y"], expected_y), \
            f"step {i}: y={b['y']} expected {expected_y}"
        assert approx(b["vx"], 5.0), f"step {i}: vx changed"
        assert approx(b["vy"], -3.0), f"step {i}: vy changed"


# ---------------------------------------------------------------------------
# 7. Free rotation (constant omega, no forces)
# ---------------------------------------------------------------------------

def test_free_rotation():
    """Spinning body with omega=2.0, no forces. Angle should advance."""
    cfg = simple_config(
        [simple_body(omega=2.0, angle=0.5)],
        width=1000.0, height=1000.0, dt=0.1)
    steps = run_sim(cfg, 5)
    for i, s in enumerate(steps):
        b = s["bodies"][0]
        expected_angle = round(0.5 + 2.0 * 0.1 * (i + 1), 6)
        assert approx(b["angle"], expected_angle, tol=1e-4), \
            f"step {i}: angle={b['angle']} expected {expected_angle}"
        assert approx(b["omega"], 2.0, tol=1e-4), \
            f"step {i}: omega changed to {b['omega']}"


# ---------------------------------------------------------------------------
# 8. Gravity accelerates downward
# ---------------------------------------------------------------------------

def test_gravity_accelerates():
    """With g=9.81, vy should increase each step."""
    cfg = simple_config(
        [simple_body(y=100.0)],
        width=1000.0, height=1000.0, dt=0.1, g=9.81)
    steps = run_sim(cfg, 5)
    prev_vy = 0.0
    for i, s in enumerate(steps):
        vy = s["bodies"][0]["vy"]
        assert vy > prev_vy, \
            f"step {i}: vy={vy} not > prev={prev_vy}"
        prev_vy = vy


# ---------------------------------------------------------------------------
# 9. Wall bounce, elastic (e=1.0)
# ---------------------------------------------------------------------------

def test_wall_bounce_elastic():
    """Body hits right wall with e=1.0. Speed should be preserved."""
    cfg = simple_config(
        [simple_body(x=25.0, y=50.0, vx=10.0, e=1.0, mu=0.0)],
        width=30.0, height=100.0, dt=0.1)
    steps = run_sim(cfg, 10)
    # After some steps, vx should become negative (bounced)
    vxs = [s["bodies"][0]["vx"] for s in steps]
    assert any(v < 0 for v in vxs), f"body never bounced: vxs={vxs}"
    # After bounce, speed should be preserved
    for i, s in enumerate(steps):
        speed = abs(s["bodies"][0]["vx"])
        assert approx(speed, 10.0, tol=0.5), \
            f"step {i}: speed={speed}, expected ~10.0"


# ---------------------------------------------------------------------------
# 10. Wall bounce with COR < 1
# ---------------------------------------------------------------------------

def test_cor_wall_bounce():
    """Body hits right wall with e=0.5. Speed should decrease after bounce."""
    cfg = simple_config(
        [simple_body(x=25.0, y=50.0, vx=10.0, e=0.5, mu=0.0)],
        width=30.0, height=100.0, dt=0.1)
    steps = run_sim(cfg, 10)
    vxs = [s["bodies"][0]["vx"] for s in steps]
    assert any(v < 0 for v in vxs), f"body never bounced: vxs={vxs}"
    # Find first post-bounce step
    for i, v in enumerate(vxs):
        if v < 0:
            post_bounce_speed = abs(v)
            # With e=0.5, speed should be roughly half
            assert post_bounce_speed < 8.0, \
                f"step {i}: post-bounce speed {post_bounce_speed} too high for e=0.5"
            assert post_bounce_speed > 2.0, \
                f"step {i}: post-bounce speed {post_bounce_speed} too low for e=0.5"
            break


# ---------------------------------------------------------------------------
# 11. Deterministic
# ---------------------------------------------------------------------------

def test_deterministic():
    """Two runs with identical config must produce identical output."""
    cfg = simple_config([
        simple_body(id=0, x=20.0, y=50.0, vx=5.0, omega=1.0),
        simple_body(id=1, x=80.0, y=50.0, vx=-3.0, mass=2.0, w=3.0, h=3.0),
    ], g=9.81)
    r1 = run_sim(cfg, 20)
    r2 = run_sim(cfg, 20)
    assert r1 == r2, "two runs with identical config produced different output"


# ---------------------------------------------------------------------------
# 12. Step count exact
# ---------------------------------------------------------------------------

def test_step_count_exact():
    cfg = simple_config([simple_body()])
    for n in (1, 10, 100):
        steps = run_sim(cfg, n)
        assert len(steps) == n, f"expected {n} steps, got {len(steps)}"


# ---------------------------------------------------------------------------
# 13. Resting body settles on floor (velocity threshold + accumulated impulse)
# ---------------------------------------------------------------------------

def test_resting_body_settles():
    """Body dropped onto floor with e=0.5 and gravity. After many steps,
    the body should settle (vy near zero) rather than bouncing forever.
    This requires velocity-dependent restitution and accumulated impulse clamping."""
    bodies = [
        simple_body(id=0, x=50.0, y=90.0, vx=0.0, vy=0.0,
                    mass=1.0, w=4.0, h=4.0, e=0.5, mu=0.1),
    ]
    cfg = simple_config(bodies, width=100.0, height=100.0, dt=0.01, g=9.81)
    steps = run_sim(cfg, 500, timeout=120)

    # Body should settle: vy should be small at the end
    final_vy = abs(steps[-1]["bodies"][0]["vy"])
    assert final_vy < 2.0, \
        f"Body didn't settle: final |vy| = {final_vy:.4f} (expected < 2.0)"

    # Body should still be near the floor, not fallen through
    final_y = steps[-1]["bodies"][0]["y"]
    assert final_y < 100.0, \
        f"Body fell through floor: y = {final_y}"
    assert final_y > 90.0, \
        f"Body flew upward: y = {final_y}"


# ---------------------------------------------------------------------------
# 14. Body-body collision separates bodies (position correction)
# ---------------------------------------------------------------------------

def test_body_body_separates():
    """Two bodies collide head-on. After the collision step, they should
    not remain deeply overlapping (position correction should push apart)."""
    bodies = [
        simple_body(id=0, x=95.0, y=100.0, vx=10.0, mass=1.0,
                    w=4.0, h=4.0, e=1.0, mu=0.0),
        simple_body(id=1, x=105.0, y=100.0, vx=-10.0, mass=1.0,
                    w=4.0, h=4.0, e=1.0, mu=0.0),
    ]
    cfg = simple_config(bodies, width=200.0, height=200.0, dt=0.05)
    steps = run_sim(cfg, 20)

    # After collision, check that bodies are separated in later steps
    for s in steps[5:]:
        b0 = next(b for b in s["bodies"] if b["id"] == 0)
        b1 = next(b for b in s["bodies"] if b["id"] == 1)
        dist = abs(b1["x"] - b0["x"])
        # Bodies have w=4 each, so centers should be >= 4.0 apart (sum of half-widths)
        # Allow some tolerance for rotation
        assert dist > 3.0, \
            f"Bodies overlapping after collision: distance={dist:.4f}"


# ---------------------------------------------------------------------------
# 15. Circle body: runs and produces output
# ---------------------------------------------------------------------------

def test_circle_runs():
    """A circle body should be accepted in the config and produce valid output."""
    bodies = [
        {"id": 0, "x": 50.0, "y": 50.0, "vx": 3.0, "vy": 0.0,
         "mass": 1.0, "shape": "circle", "r": 2.0, "e": 1.0, "mu": 0.0},
    ]
    cfg = simple_config(bodies, width=200.0, height=200.0)
    steps = run_sim(cfg, 5)
    assert len(steps) == 5
    for s in steps:
        assert len(s["bodies"]) == 1
        for key in ("id", "x", "y", "vx", "vy", "angle", "omega"):
            assert key in s["bodies"][0]


# ---------------------------------------------------------------------------
# 16. Circle free motion (same as rect)
# ---------------------------------------------------------------------------

def test_circle_free_motion():
    """Circle with velocity, no gravity, no walls nearby. Linear motion."""
    bodies = [
        {"id": 0, "x": 100.0, "y": 100.0, "vx": 5.0, "vy": -2.0,
         "mass": 1.0, "shape": "circle", "r": 1.0, "e": 1.0, "mu": 0.0},
    ]
    cfg = simple_config(bodies, width=400.0, height=400.0, dt=0.1)
    steps = run_sim(cfg, 5)
    for i, s in enumerate(steps):
        b = s["bodies"][0]
        expected_x = round(100.0 + 5.0 * 0.1 * (i + 1), 6)
        expected_y = round(100.0 + (-2.0) * 0.1 * (i + 1), 6)
        assert approx(b["x"], expected_x), f"step {i}: x={b['x']} expected {expected_x}"
        assert approx(b["y"], expected_y), f"step {i}: y={b['y']} expected {expected_y}"


# ---------------------------------------------------------------------------
# 17. Circle-circle collision
# ---------------------------------------------------------------------------

def test_circle_circle_collision():
    """Two circles approach head-on. After collision, velocities should swap
    (elastic, equal mass)."""
    bodies = [
        {"id": 0, "x": 45.0, "y": 100.0, "vx": 10.0, "vy": 0.0,
         "mass": 1.0, "shape": "circle", "r": 3.0, "e": 1.0, "mu": 0.0},
        {"id": 1, "x": 55.0, "y": 100.0, "vx": -10.0, "vy": 0.0,
         "mass": 1.0, "shape": "circle", "r": 3.0, "e": 1.0, "mu": 0.0},
    ]
    cfg = simple_config(bodies, width=200.0, height=200.0, dt=0.01)
    steps = run_sim(cfg, 30)
    # After collision, body 0 should move left, body 1 right
    vxs_0 = [s["bodies"][0]["vx"] for s in steps]
    assert any(v < 0 for v in vxs_0), "circle 0 never bounced back"


# ---------------------------------------------------------------------------
# 18. Circle wall bounce
# ---------------------------------------------------------------------------

def test_circle_wall_bounce():
    """Circle bounces off right wall with e=1.0. Speed preserved."""
    bodies = [
        {"id": 0, "x": 95.0, "y": 50.0, "vx": 10.0, "vy": 0.0,
         "mass": 1.0, "shape": "circle", "r": 2.0, "e": 1.0, "mu": 0.0},
    ]
    cfg = simple_config(bodies, width=100.0, height=100.0, dt=0.1)
    steps = run_sim(cfg, 10)
    vxs = [s["bodies"][0]["vx"] for s in steps]
    assert any(v < 0 for v in vxs), "circle never bounced off right wall"
    for s in steps:
        speed = abs(s["bodies"][0]["vx"])
        assert approx(speed, 10.0, tol=0.5), f"speed not preserved: {speed}"


# ---------------------------------------------------------------------------
# 19. Circle-rectangle collision
# ---------------------------------------------------------------------------

def test_circle_rect_collision():
    """Circle hits a rectangle. Both should change velocity."""
    bodies = [
        {"id": 0, "x": 45.0, "y": 100.0, "vx": 10.0, "vy": 0.0,
         "mass": 1.0, "shape": "circle", "r": 3.0, "e": 1.0, "mu": 0.0},
        simple_body(id=1, x=55.0, y=100.0, vx=-5.0, mass=1.0,
                    w=4.0, h=4.0, e=1.0, mu=0.0),
    ]
    cfg = simple_config(bodies, width=200.0, height=200.0, dt=0.01)
    steps = run_sim(cfg, 50)
    # After collision, circle should bounce back
    vxs_0 = [s["bodies"][0]["vx"] for s in steps]
    assert any(v < 0 for v in vxs_0), "circle never bounced off rectangle"
