"""Public normal, edge, invariant, and determinism tests."""

from __future__ import annotations

import copy
import math

from collision_kernels import clamp_friction, clamp_normal, circle_box_manifold
from physics2d import simulate


def _circle(**values):
    return {"id": 0, "shape": "circle", "x": 46.0, "y": 50.0, "vx": 8.0,
            "vy": 0.0, "angle": 0.0, "omega": 0.0, "mass": 1.0, "r": 3.0,
            "e": 0.5, "mu": 0.4} | values


def _box(**values):
    return {"id": 1, "shape": "rect", "x": 50.0, "y": 50.0, "vx": 0.0,
            "vy": 0.0, "angle": 0.0, "omega": 0.0, "mass": 2.0, "w": 4.0,
            "h": 8.0, "e": 0.5, "mu": 0.4} | values


def _config(bodies, iterations=12):
    return {"width": 200.0, "height": 200.0, "dt": 0.01, "g": 0.0,
            "solver_iterations": iterations, "bodies": bodies}


def test_normal_axis_aligned_circle_box_contact() -> None:
    hit = circle_box_manifold(_circle(), _box())
    assert hit is not None
    normal, depth, point = hit
    assert normal == (-1.0, 0.0)
    assert abs(depth - 1.0) < 1e-12
    assert point == (49.0, 50.0)


def test_edge_inside_rotated_box_uses_nearest_face() -> None:
    box = _box(angle=math.pi / 2, w=8.0, h=4.0)
    hit = circle_box_manifold(_circle(x=50.0, y=53.8, r=0.5), box)
    assert hit is not None
    normal, depth, _ = hit
    assert normal[1] > 0.999 and abs(normal[0]) < 1e-10
    assert abs(depth - 0.7) < 1e-10


def test_invariant_many_iterations_do_not_add_energy() -> None:
    assert clamp_normal(5.0, -8.0) == (0.0, -5.0)
    assert clamp_friction(2.0, 4.0, 0.5, 6.0) == (3.0, 1.0)
    bodies = [_circle(x=48.0, vx=8.0, e=0.6), _box(x=52.0, vx=-4.0, e=0.6)]
    initial = sum(0.5 * b["mass"] * (b["vx"] ** 2 + b["vy"] ** 2) for b in bodies)
    final = simulate(_config(bodies, iterations=30), copy.deepcopy(bodies), 1)[0]
    mass = {body["id"]: body["mass"] for body in bodies}
    energy = sum(0.5 * mass[b["id"]] * (b["vx"] ** 2 + b["vy"] ** 2)
                 for b in final["bodies"])
    assert energy <= initial + 1e-5


def test_deterministic_and_input_order_independent() -> None:
    bodies = [_circle(), _box(), _circle(id=2, x=100.0, y=100.0)]
    first = simulate(_config(bodies), copy.deepcopy(bodies), 20)
    second = simulate(_config(list(reversed(bodies))), copy.deepcopy(sorted(bodies, key=lambda b: b["id"])), 20)
    assert first == second
