# Collision kernels

Repair the manifold and impulse functions in `collision_kernels.py`; it is the only editable file. `physics2d.py` supplies the complete deterministic engine.

`circle_box_manifold(circle, box)` transforms into box-local coordinates, clamps to the half-extents, and returns `(normal, penetration, contact)` only for strict overlap. The unit normal points from box to circle in world space. For an inside center, choose the nearest face with deterministic x-before-y tie-breaking; penetration is `radius + distance_to_face`. Contact is always `circle_center - radius * normal`.

`clamp_normal` and `clamp_friction` add raw increments, clamp the new accumulator, and return `(new, new-old)`. `solve_contact(...)` performs one sequential impulse iteration. Include angular contact velocity and effective mass, low-speed restitution suppression, and geometric material combination. Clamp accumulated normal impulse to `[0,+inf)` and accumulated tangent impulse to `[-sqrt(muA*muB)*accN,+sqrt(muA*muB)*accN]`; apply only each accumulator delta. Recompute contact velocity after the normal delta and preserve accumulators when separating or tangential speed is negligible.

Use stdlib only, keep calculations finite and deterministic, and run `python3 -m pytest -q /app/files/tests.py`.
