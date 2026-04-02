# N-Body Physics Simulator — Repair Deterministic Simulation

Fix the broken Rust n-body gravitational simulator so it compiles, runs, and produces
deterministic trajectories matching reference output within strict tolerance.

## Setup

The Rust project dependencies are pre-compiled at `/app/`. Copy the starter source code
into the project and build:

```bash
cp /app/files/Cargo.toml /app/Cargo.toml
cp -r /app/files/src /app/src
cd /app && cargo build --release
```

The binary will be at `/app/target/release/nbody_sim`.

## Usage

```bash
./target/release/nbody_sim --input <seed.json> [--output <out.json>]
```

If `--output` is omitted, JSON is printed to stdout.

## What the Simulator Does

- Reads initial conditions from a JSON seed file: body masses, positions, velocities, plus
  simulation config (timestep dt, number of steps, collision threshold, gravitational constant).
- Runs N timesteps of gravitational n-body simulation using Velocity Verlet integration.
- Outputs JSON: `{steps: [{time, bodies: [{position, velocity, ke, pe}...], total_energy}...], collisions: [...]}`
- Detects collisions when two bodies come within the threshold distance.
- Must produce **deterministic** f64 output (identical across runs on the same input).

## Known Issues

The starter code has several bugs that cause incorrect simulation results.
Fix all bugs so the simulator produces output matching the reference trajectories.

## Requirements

- `cargo build --release` succeeds without errors
- Simulator runs on seed files without panicking
- Two runs on the same seed produce byte-identical output
- Trajectories match `/app/files/fixtures/reference_01.json` within 1e-10 tolerance
- Total energy is conserved (drift < 1e-8 over the simulation)
- Output is valid JSON with the expected schema
- Invalid inputs (negative mass, zero timestep) are rejected with a clear error message

## Verification

Run the visible tests:

    python3 -m pytest /app/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest.

## Continuous Collision Detection (Anti-Tunneling)

The simulator must detect collisions that happen MID-STEP via continuous collision detection (CCD).
CCD is the **only** collision detection mechanism — do NOT also check step endpoints (that would double-count). One collision per pair per step at most.

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic (no threading non-determinism, no HashMap iteration).
- Do not modify test or verifier files.
