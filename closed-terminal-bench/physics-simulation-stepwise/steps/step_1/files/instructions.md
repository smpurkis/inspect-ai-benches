# N-Body Physics Simulator — Step 1: Repair Deterministic Simulation

Fix the broken Rust n-body gravitational simulator so it compiles, runs, and produces
deterministic trajectories matching reference output within strict tolerance.

## Setup

The Rust project dependencies are pre-compiled at `/app/`. Copy the starter source code
into the project and build:

```bash
cp /app/step_1/files/Cargo.toml /app/Cargo.toml
cp -r /app/step_1/files/src /app/src
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

The starter code has several bugs that cause incorrect simulation results:
- Incorrect force calculation (Newton's law of gravitation)
- Wrong integration step ordering (Velocity Verlet algorithm)
- Arithmetic error in position update
- Incorrect energy computation
- Insufficient output precision

Fix all bugs so the simulator produces output matching the reference trajectories.

## Requirements

- `cargo build --release` succeeds without errors
- Simulator runs on seed files without panicking
- Two runs on the same seed produce byte-identical output
- Trajectories match `/app/step_1/files/fixtures/reference_01.json` within 1e-10 tolerance
- Total energy is conserved (drift < 1e-8 over the simulation)
- Output is valid JSON with the expected schema
- Invalid inputs (negative mass, zero timestep) are rejected with a clear error message

## Verification

Run the visible tests:

    python3 -m pytest /app/step_1/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest.

## Scoring

- Step 1 fail → 0
- Step 1 pass, Step 2 fail → 1/3
- Step 1+2 pass, Step 3 fail → 2/3
- All pass → 1.0

## Continuous Collision Detection (Anti-Tunneling)

The simulator must detect collisions that happen MID-STEP, not just at step boundaries.
Two fast-moving bodies may pass through each other (through the collision threshold) during
a timestep but end up far apart at the end of the step.

Fix `check_continuous_collision` in sim.rs to compute the true minimum approach distance
using the quadratic minimum formula:
- t* = -dot(r0, Δv·dt) / |Δv·dt|², clamped to [0,1]
- where r0 = relative position at step start, Δv = relative velocity

If the minimum distance at t* is less than collision_threshold, record a collision.

**Important:** CCD is the **only** collision detection mechanism. Do NOT additionally check
whether bodies are within threshold distance at step endpoints. Checking endpoints as well
as CCD would double-count collisions that occur during a step. One collision is recorded per
pair per step at most, using the CCD formula above.

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic (no threading non-determinism, no HashMap iteration).
- Do not modify test or verifier files.
