"""Generated and metamorphic checks for the exposed collision kernels."""

from __future__ import annotations

import ast
import copy
import math
import random
import sys
from pathlib import Path

import pytest

FILES = Path(__file__).resolve().parents[1] / "files"
sys.path.insert(0, str(FILES))
from collision_kernels import clamp_friction, clamp_normal, circle_box_manifold  # noqa: E402
from physics2d import manifold, simulate  # noqa: E402


def circle(identifier=0, **values):
    return {"id": identifier, "shape": "circle", "x": 0.0, "y": 0.0,
            "vx": 0.0, "vy": 0.0, "angle": 0.0, "omega": 0.0, "mass": 1.0,
            "r": 1.0, "e": 0.7, "mu": 0.5} | values


def box(identifier=1, **values):
    return {"id": identifier, "shape": "rect", "x": 0.0, "y": 0.0,
            "vx": 0.0, "vy": 0.0, "angle": 0.0, "omega": 0.0, "mass": 2.0,
            "w": 4.0, "h": 2.0, "e": 0.7, "mu": 0.5} | values


def config(bodies, iterations=16):
    return {"width": 1000.0, "height": 1000.0, "dt": 0.01, "g": 0.0,
            "solver_iterations": iterations, "bodies": bodies}


def rotate(point, angle):
    c, s = math.cos(angle), math.sin(angle)
    return c * point[0] - s * point[1], s * point[0] + c * point[1]


def test_trusted_engine_reaches_both_candidate_kernels() -> None:
    source = (FILES / "physics2d.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {node.func.id for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert {"circle_box_manifold", "solve_contact"} <= names
    kernel_source = (FILES / "collision_kernels.py").read_text(encoding="utf-8")
    assert "clamp_normal(" in kernel_source and "clamp_friction(" in kernel_source


@pytest.mark.parametrize("seed", range(20))
def test_generated_scalar_accumulator_oracle(seed: int) -> None:
    rng = random.Random(seed)
    normal = rng.uniform(0, 50)
    tangent = rng.uniform(-normal, normal)
    for _ in range(200):
        raw_n = rng.uniform(-20, 20)
        old_n = normal
        normal, delta_n = clamp_normal(normal, raw_n)
        assert normal == max(0.0, old_n + raw_n)
        assert delta_n == normal - old_n
        mu = rng.uniform(0, 2)
        raw_t = rng.uniform(-20, 20)
        old_t = tangent
        tangent, delta_t = clamp_friction(tangent, raw_t, mu, normal)
        limit = mu * normal
        assert tangent == max(-limit, min(limit, old_t + raw_t))
        assert delta_t == tangent - old_t


@pytest.mark.parametrize("seed", range(12))
def test_generated_manifolds_against_local_space_oracle(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(100):
        angle = rng.uniform(-math.pi, math.pi)
        rectangle = box(angle=angle, w=rng.uniform(0.5, 15), h=rng.uniform(0.5, 15),
                        x=rng.uniform(-20, 20), y=rng.uniform(-20, 20))
        local = (rng.uniform(-10, 10), rng.uniform(-10, 10))
        world_delta = rotate(local, angle)
        item = circle(x=rectangle["x"] + world_delta[0], y=rectangle["y"] + world_delta[1],
                      r=rng.uniform(0.05, 4))
        closest = (max(-rectangle["w"] / 2, min(rectangle["w"] / 2, local[0])),
                   max(-rectangle["h"] / 2, min(rectangle["h"] / 2, local[1])))
        distance = math.hypot(local[0] - closest[0], local[1] - closest[1])
        expected = distance < item["r"]
        result = circle_box_manifold(item, rectangle)
        assert (result is not None) == expected
        if result:
            normal, depth, point = result
            assert abs(math.hypot(*normal) - 1.0) < 1e-9
            assert depth > 0 and math.isfinite(depth)
            assert abs(math.hypot(point[0] - item["x"], point[1] - item["y"]) - item["r"]) < 1e-8


@pytest.mark.parametrize("angle", [0.17, math.pi / 4, math.pi / 2, 2.4])
def test_metamorphic_rigid_rotation_of_manifold(angle: float) -> None:
    item, rectangle = circle(x=3.2, y=1.1, r=1.3), box(angle=0.31, w=6, h=3)
    original = circle_box_manifold(item, rectangle)
    assert original is not None
    cx, cy = rotate((item["x"], item["y"]), angle)
    bx, by = rotate((rectangle["x"], rectangle["y"]), angle)
    transformed = circle_box_manifold(dict(item, x=cx, y=cy),
                                      dict(rectangle, x=bx, y=by, angle=rectangle["angle"] + angle))
    assert transformed is not None
    expected_normal, expected_point = rotate(original[0], angle), rotate(original[2], angle)
    assert math.dist(transformed[0], expected_normal) < 1e-9
    assert abs(transformed[1] - original[1]) < 1e-9
    assert math.dist(transformed[2], expected_point) < 1e-9


@pytest.mark.parametrize("local,expected", [((0, 0), 1.0), ((1.9, 0), 0.1), ((0, 0.9), 0.1)])
def test_inside_cases_choose_minimum_translation(local, expected) -> None:
    rectangle = box(w=4, h=2, angle=0.63)
    delta = rotate(local, rectangle["angle"])
    hit = circle_box_manifold(circle(x=delta[0], y=delta[1], r=1), rectangle)
    assert hit is not None and abs(hit[1] - (1 + expected)) < 1e-9


def _energy(record, originals):
    props = {body["id"]: body for body in originals}
    total = 0.0
    for state in record["bodies"]:
        body = props[state["id"]]
        inertia = (0.5 * body["mass"] * body["r"] ** 2 if body["shape"] == "circle"
                   else body["mass"] * (body["w"] ** 2 + body["h"] ** 2) / 12)
        total += 0.5 * body["mass"] * (state["vx"] ** 2 + state["vy"] ** 2)
        total += 0.5 * inertia * state["omega"] ** 2
    return total


@pytest.mark.parametrize("iterations", [2, 5, 20, 50])
def test_generated_accumulation_is_bounded_and_iteration_stable(iterations: int) -> None:
    bodies = [circle(x=498.0, y=499.2, vx=10, vy=2, r=3, e=0.4),
              box(x=502.0, y=500.0, vx=-5, vy=-1, w=5, h=4, e=0.4)]
    initial = _energy({"bodies": bodies}, bodies)
    final = simulate(config(bodies, iterations), copy.deepcopy(bodies), 1)[0]
    assert _energy(final, bodies) <= initial + 2e-4
    reference = simulate(config(bodies, 60), copy.deepcopy(bodies), 1)[0]
    if iterations >= 20:
        for actual, expected in zip(final["bodies"], reference["bodies"]):
            assert abs(actual["vx"] - expected["vx"]) < 2e-4
            assert abs(actual["vy"] - expected["vy"]) < 2e-4


def test_friction_accumulator_respects_current_normal_cone() -> None:
    bodies = [circle(x=498, y=498, vx=12, vy=7, r=3, e=0, mu=0.8),
              box(x=502, y=500, vx=-3, vy=-2, w=5, h=5, e=0, mu=0.8)]
    steps = simulate(config(bodies, 40), copy.deepcopy(bodies), 8)
    assert all(_energy(step, bodies) <= _energy({"bodies": bodies}, bodies) + 1e-3 for step in steps)
    assert any(abs(body["omega"]) > 0.05 for body in steps[-1]["bodies"])


def test_pair_order_and_circle_box_argument_swap_invariants() -> None:
    a, b = circle(x=499, vx=8), box(x=501, vx=-2)
    direct, swapped = manifold(a, b), manifold(b, a)
    assert direct and swapped
    assert math.dist(direct[0], (-swapped[0][0], -swapped[0][1])) < 1e-12
    assert abs(direct[1] - swapped[1]) < 1e-12
    first = simulate(config([a, b]), copy.deepcopy([a, b]), 5)
    second = simulate(config([b, a]), copy.deepcopy(sorted([b, a], key=lambda x: x["id"])), 5)
    assert first == second
