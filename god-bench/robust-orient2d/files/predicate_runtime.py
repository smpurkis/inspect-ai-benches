#!/usr/bin/env python3
"""Protected JSON-lines adapter for the candidate predicates."""

from __future__ import annotations

import json
import sys

from predicates import classify_segments, orient2d


def point(value: object) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("a point must be a two-element JSON array")
    return float(value[0]), float(value[1])


for line in sys.stdin:
    try:
        request = json.loads(line)
        operation = request["op"]
        points = [point(value) for value in request["points"]]
        if operation == "orient" and len(points) == 3:
            result = orient2d(*points)
        elif operation == "segments" and len(points) == 4:
            result = classify_segments(*points)
        else:
            raise ValueError("invalid operation or point count")
        response = {"ok": True, "result": result}
    except Exception as error:
        response = {"ok": False, "error": f"{type(error).__name__}: {error}"}
    print(json.dumps(response, separators=(",", ":"), sort_keys=True), flush=True)
