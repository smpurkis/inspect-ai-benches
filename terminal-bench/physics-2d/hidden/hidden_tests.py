"""Hidden tests for physics-2d: advanced physics correctness checks.

These tests are NOT visible to the agent. They verify OBB collision detection,
rotational dynamics, conservation laws, friction, multi-body stability,
accumulated impulse clamping, velocity-dependent restitution, position
correction, and circle-rectangle collision handling.
"""

import json
import subprocess
import os
import tempfile
import math
import pytest

SCRIPT = "/app/files/physics2d.py"


def run_sim(config: dict, steps: int, *, timeout=120):
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
        assert len(lines) == steps, f"expected {steps} lines, got {len(lines)}"
        return [json.loads(l) for l in lines]
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
