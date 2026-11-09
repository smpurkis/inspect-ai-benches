"""Trusted deterministic 2D engine; candidate work lives in collision_kernels.py."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from collision_kernels import circle_box_manifold, solve_contact

Body = dict[str, Any]
Manifold = tuple[tuple[float, float], float, tuple[float, float]]
EPS = 1e-10


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _inertia(body: Body) -> float:
    if body["shape"] == "circle":
        return 0.5 * body["mass"] * body["r"] ** 2
    return body["mass"] * (body["w"] ** 2 + body["h"] ** 2) / 12.0


def _vertices(body: Body) -> list[tuple[float, float]]:
    c, s = math.cos(body["angle"]), math.sin(body["angle"])
    hw, hh = body["w"] / 2.0, body["h"] / 2.0
    return [
        (body["x"] + sx * hw * c - sy * hh * s,
         body["y"] + sx * hw * s + sy * hh * c)
        for sx, sy in ((1, -1), (-1, -1), (-1, 1), (1, 1))
    ]


def _mean_support(vertices, axis, want_min):
    projections = [_dot(vertex, axis) for vertex in vertices]
    target = min(projections) if want_min else max(projections)
    tied = [v for v, p in zip(vertices, projections) if abs(p - target) <= EPS]
    return (sum(v[0] for v in tied) / len(tied), sum(v[1] for v in tied) / len(tied))


def _rect_rect(a: Body, b: Body) -> Manifold | None:
    va, vb = _vertices(a), _vertices(b)
    axes = []
    for body in (a, b):
        c, s = math.cos(body["angle"]), math.sin(body["angle"])
        axes.extend(((c, s), (-s, c)))
    best_axis, best_depth = None, math.inf
    for axis in axes:
        pa, pb = [_dot(v, axis) for v in va], [_dot(v, axis) for v in vb]
        overlap = min(max(pa), max(pb)) - max(min(pa), min(pb))
        if overlap <= 0.0:
            return None
        if overlap < best_depth:
            best_axis, best_depth = axis, overlap
    assert best_axis is not None
    delta = (a["x"] - b["x"], a["y"] - b["y"])
    normal = best_axis if _dot(best_axis, delta) >= 0.0 else (-best_axis[0], -best_axis[1])
    sa = _mean_support(va, normal, True)
    sb = _mean_support(vb, normal, False)
    return normal, best_depth, ((sa[0] + sb[0]) / 2.0, (sa[1] + sb[1]) / 2.0)


def _circle_circle(a: Body, b: Body) -> Manifold | None:
    dx, dy = a["x"] - b["x"], a["y"] - b["y"]
    distance = math.hypot(dx, dy)
    radius = a["r"] + b["r"]
    if distance >= radius:
        return None
    normal = (1.0, 0.0) if distance <= EPS else (dx / distance, dy / distance)
    weight = b["r"] / radius
    point = (b["x"] + weight * dx, b["y"] + weight * dy)
    return normal, radius - distance, point


def manifold(a: Body, b: Body) -> Manifold | None:
    if a["shape"] == b["shape"] == "rect":
        return _rect_rect(a, b)
    if a["shape"] == b["shape"] == "circle":
        return _circle_circle(a, b)
    if a["shape"] == "circle":
        return circle_box_manifold(a, b)
    result = circle_box_manifold(b, a)
    if result is None:
        return None
    normal, depth, point = result
    return (-normal[0], -normal[1]), depth, point


def _correct_pairs(bodies: list[Body]) -> None:
    for index, a in enumerate(bodies):
        for b in bodies[index + 1:]:
            hit = manifold(a, b)
            if hit is None:
                continue
            normal, depth, _ = hit
            correction = max(depth - 0.005, 0.0) * 0.2
            ia, ib = 1.0 / a["mass"], 1.0 / b["mass"]
            scale = correction / (ia + ib)
            a["x"] += normal[0] * scale * ia
            a["y"] += normal[1] * scale * ia
            b["x"] -= normal[0] * scale * ib
            b["y"] -= normal[1] * scale * ib


def resolve_body_collisions(bodies: list[Body], iterations: int) -> None:
    accumulators: dict[tuple[int, int], tuple[float, float]] = {}
    for _ in range(iterations):
        for index, a in enumerate(bodies):
            for b in bodies[index + 1:]:
                hit = manifold(a, b)
                if hit is None:
                    continue
                key = (a["id"], b["id"])
                accumulators[key] = solve_contact(
                    a, b, hit[0], hit[2], accumulators.get(key, (0.0, 0.0)),
                    _inertia(a), _inertia(b),
                )
    _correct_pairs(bodies)


def _wall_contact(body: Body, wall: str, width: float, height: float):
    normals = {"left": (1.0, 0.0), "right": (-1.0, 0.0),
               "top": (0.0, 1.0), "bottom": (0.0, -1.0)}
    normal = normals[wall]
    if body["shape"] == "circle":
        penetration = {"left": body["r"] - body["x"],
                       "right": body["x"] + body["r"] - width,
                       "top": body["r"] - body["y"],
                       "bottom": body["y"] + body["r"] - height}[wall]
        point = (body["x"] - body["r"] * normal[0],
                 body["y"] - body["r"] * normal[1])
        return normal, penetration, point
    vertices = _vertices(body)
    values = {"left": [-x for x, _ in vertices],
              "right": [x - width for x, _ in vertices],
              "top": [-y for _, y in vertices],
              "bottom": [y - height for _, y in vertices]}[wall]
    penetration = max(values)
    tied = [v for v, value in zip(vertices, values) if abs(value - penetration) <= EPS]
    point = (sum(v[0] for v in tied) / len(tied), sum(v[1] for v in tied) / len(tied))
    return normal, penetration, point


def resolve_walls(bodies: list[Body], width: float, height: float) -> None:
    for body in bodies:
        inertia = _inertia(body)
        for wall in ("left", "right", "top", "bottom"):
            normal, penetration, point = _wall_contact(body, wall, width, height)
            if penetration <= 0.0:
                continue
            r = (point[0] - body["x"], point[1] - body["y"])
            contact_v = (body["vx"] - body["omega"] * r[1],
                         body["vy"] + body["omega"] * r[0])
            vn = _dot(contact_v, normal)
            normal_impulse = 0.0
            if vn < 0.0:
                restitution = 0.0 if abs(vn) < 1.0 else body["e"]
                denom = 1.0 / body["mass"] + _cross(r, normal) ** 2 / inertia
                normal_impulse = -(1.0 + restitution) * vn / denom
                impulse = (normal_impulse * normal[0], normal_impulse * normal[1])
                body["vx"] += impulse[0] / body["mass"]
                body["vy"] += impulse[1] / body["mass"]
                body["omega"] += _cross(r, impulse) / inertia
                contact_v = (body["vx"] - body["omega"] * r[1],
                             body["vy"] + body["omega"] * r[0])
                tangent_v = (contact_v[0] - _dot(contact_v, normal) * normal[0],
                             contact_v[1] - _dot(contact_v, normal) * normal[1])
                length = math.hypot(*tangent_v)
                if length > EPS:
                    tangent = (tangent_v[0] / length, tangent_v[1] / length)
                    denom = 1.0 / body["mass"] + _cross(r, tangent) ** 2 / inertia
                    jt = max(-body["mu"] * normal_impulse,
                             min(body["mu"] * normal_impulse, -length / denom))
                    impulse = (jt * tangent[0], jt * tangent[1])
                    body["vx"] += impulse[0] / body["mass"]
                    body["vy"] += impulse[1] / body["mass"]
                    body["omega"] += _cross(r, impulse) / inertia
            body["x"] += normal[0] * penetration
            body["y"] += normal[1] * penetration


def load_config(path: str | Path) -> tuple[dict[str, Any], list[Body]]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    bodies = []
    for raw in config["bodies"]:
        body = dict(raw)
        body.setdefault("shape", "rect")
        for key, default in (("angle", 0.0), ("omega", 0.0), ("e", 1.0), ("mu", 0.0)):
            body.setdefault(key, default)
        bodies.append(body)
    bodies.sort(key=lambda item: item["id"])
    return config, bodies


def advance(config: dict[str, Any], bodies: list[Body]) -> None:
    dt = float(config["dt"])
    for body in bodies:
        body["vy"] += float(config["g"]) * dt
        body["x"] += body["vx"] * dt
        body["y"] += body["vy"] * dt
        body["angle"] += body["omega"] * dt
    resolve_body_collisions(bodies, int(config.get("solver_iterations", 10)))
    resolve_walls(bodies, float(config["width"]), float(config["height"]))


def simulate(config: dict[str, Any], bodies: list[Body], steps: int) -> list[dict]:
    records = []
    for step in range(steps):
        advance(config, bodies)
        records.append({"step": step, "bodies": [
            {"id": body["id"], **{key: round(float(body[key]), 6)
             for key in ("x", "y", "vx", "vy", "angle", "omega")}}
            for body in bodies
        ]})
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--steps", required=True, type=int)
    args = parser.parse_args()
    config, bodies = load_config(args.config)
    records = simulate(config, bodies, args.steps)
    Path(args.output).write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
