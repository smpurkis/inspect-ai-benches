Repair `collision_kernels.py`, the only editable file. Complete the circle-versus-rotated-box manifold and accumulated normal/friction sequential-impulse update described in `TASK.md`; the engine, CLI, walls, other shape pairs, integration, and serialization are supplied.

Keep normals oriented box-to-circle, handle inside/face/corner contacts, apply only accumulator deltas, and clamp friction by the current accumulated normal impulse. Work offline with stdlib only. Run `python3 -m pytest -q /app/files/tests.py`.
