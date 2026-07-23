Implement `physics2d.py`; it is the only editable file.

Run `python3 /app/files/physics2d.py --config <config.json> --output
<output.jsonl> --steps <N>`.
Implement the deterministic semi-implicit 2D rigid-body solver defined in
`physics_spec.md`: rectangle/circle contacts, rotation, restitution, Coulomb
friction, accumulated impulses, position correction, and walls.

`contract.toml` defines limits and fixed policies. `schema.json` defines config
and JSONL record schemas. `physics_spec.md` is authoritative for numerical
behavior and tie-breaking.

Use Python stdlib and NumPy only; work offline. Preserve body IDs, emit exactly
one schema-valid record per step, sort bodies by ID, keep all state finite, round
state floats to six decimals, and do not modify tests, schemas, or specifications.

Run `python3 -m pytest -q /app/files/tests.py`.
