"""Starter for the deterministic solver specified by physics_spec.md."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


Body = dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--steps", required=True, type=int)
    return parser.parse_args()


def load_config(path: str | Path) -> tuple[dict[str, Any], list[Body]]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    bodies: list[Body] = []
    for raw in config["bodies"]:
        body = dict(raw)
        body.setdefault("shape", "rect")
        body.setdefault("angle", 0.0)
        body.setdefault("omega", 0.0)
        body.setdefault("e", 1.0)
        body.setdefault("mu", 0.0)
        bodies.append(body)
    bodies.sort(key=lambda body: body["id"])
    return config, bodies


def resolve_body_collisions(
    bodies: list[Body], solver_iterations: int
) -> None:
    """Resolve all contacts in ascending body-ID pair order."""

    # TODO: implement the accumulated sequential impulse solver.


def resolve_walls(bodies: list[Body], width: float, height: float) -> None:
    """Resolve left, right, top, then bottom wall contacts."""

    # TODO: implement wall impulses, friction, and position correction.


def advance(config: dict[str, Any], bodies: list[Body]) -> None:
    dt = float(config["dt"])
    gravity = float(config["g"])
    for body in bodies:
        body["vy"] = float(body["vy"]) + gravity * dt
        body["x"] = float(body["x"]) + float(body["vx"]) * dt
        body["y"] = float(body["y"]) + float(body["vy"]) * dt
        body["angle"] = float(body["angle"]) + float(body["omega"]) * dt

    resolve_body_collisions(bodies, int(config.get("solver_iterations", 10)))
    resolve_walls(bodies, float(config["width"]), float(config["height"]))


def output_record(step: int, bodies: list[Body]) -> dict[str, Any]:
    keys = ("x", "y", "vx", "vy", "angle", "omega")
    return {
        "step": step,
        "bodies": [
            {
                "id": body["id"],
                **{key: round(float(body[key]), 6) for key in keys},
            }
            for body in bodies
        ],
    }


def simulate(
    config: dict[str, Any], bodies: list[Body], steps: int
) -> list[dict[str, Any]]:
    records = []
    for step in range(steps):
        advance(config, bodies)
        records.append(output_record(step, bodies))
    return records


def main() -> None:
    args = parse_args()
    if args.steps < 0:
        raise ValueError("--steps must be non-negative")
    config, bodies = load_config(args.config)
    records = simulate(config, bodies, args.steps)
    text = "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records)
    Path(args.output).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
