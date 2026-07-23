# General-Relativity ODE Repair

Edit only `src/lib.rs`. Implement `solve_tov`, `os_collapse`, `polytropic_eos`, `rk45_step`, and any private helpers while preserving the public Rust API and `gr_sim --input <seed.json> [--output <out.json>]` CLI.

Produce the JSON schema defined by `src/types.rs`. TOV results must support uniform-density and polytropic equations of state, surface interpolation, Schwarzschild lapse matching, baryon mass, and a 50-point profile. Collapse results must satisfy the Oppenheimer-Snyder trajectory, horizon event, singularity time, and energy conservation. `CollapseConfig.num_steps` controls the internal numerical integration resolution; it is not the serialized trajectory length. Return exactly 51 ordered trajectory samples, including the initial state and the final near-singularity state, regardless of `num_steps`. Outputs must be finite, deterministic, and physically admissible. New dependencies and network access are forbidden.

Build with `cp /app/files/Cargo.toml /app/Cargo.toml && mkdir -p /app/src && cp /app/files/src/*.rs /app/src/ && cd /app && cargo build --release --offline`.

Run `python3 -m pytest -q /app/files/tests.py`.
