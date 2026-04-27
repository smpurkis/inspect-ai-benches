# General-Relativity Stellar Collapse Simulator

Implement a two-phase general-relativity simulation in Rust: a static stellar
equilibrium solver (TOV equations) and an Oppenheimer-Snyder dust-ball collapse
integrator.  All physics is in **geometric units** (G = c = 1).

## Setup

The Rust project dependencies are pre-compiled at `/app/`.  Copy the starter
source code into the project and build:

```bash
cp /app/files/Cargo.toml /app/Cargo.toml
cp -r /app/files/src /app/src
cd /app && cargo build --release
```

The binary will be at `/app/target/release/gr_sim`.

## Usage

```bash
./target/release/gr_sim --input <seed.json> [--output <out.json>]
```

If `--output` is omitted, JSON is printed to stdout.

The seed JSON specifies which mode to run (`"tov"`, `"collapse"`, or `"both"`)
together with the physical parameters.  See the fixture files under
`/app/files/fixtures/` for concrete examples.

## What You Must Implement

All implementation goes in **`src/lib.rs`**.  Do **not** modify `src/main.rs` or
`src/types.rs`.  The only allowed crate dependencies are `serde`, `serde_json`,
and `clap` (already in `Cargo.toml`).

### Phase 1 --- TOV Stellar Equilibrium

Solve the Tolman-Oppenheimer-Volkoff equations for a static, spherically
symmetric star.  Three coupled first-order ODEs in the areal radius r:

    dm/dr   = 4 pi r^2 rho

    dP/dr   = -(rho + P)(m + 4 pi r^3 P) / [ r (r - 2 m) ]

    dphi/dr = (m + 4 pi r^3 P) / [ r (r - 2 m) ]

where m(r) is the enclosed gravitational mass, P(r) is pressure, and phi(r) is
the metric potential (the lapse is exp(phi)).

**Equation of state.**  Two modes are supported:

- **Polytropic:** P = K rho_0^Gamma, where rho_0 is the rest-mass density.
  The total energy density is rho = rho_0 + P / (Gamma - 1).

- **Uniform density:** rho = central_density (constant throughout).  The
  central pressure P_c is given explicitly in the seed JSON
  (`central_pressure` field).

**Boundary / initial conditions at r = 0:**  The TOV equations are singular at
the origin.  Start the integration at a small offset r_start with:

    P(r_start) = P_c
    m(r_start) = (4/3) pi rho_c r_start^3     (rho_c is the central energy density)
    phi(r_start) = 0                            (shifted to match exterior later)

**Surface detection:** Integrate outward until P drops to zero (or below).
Interpolate to find the stellar radius R where P = 0.

**Metric matching:** After integration, shift phi so that at the surface
phi(R) = 0.5 ln(1 - 2 M / R), matching the exterior Schwarzschild solution.
The lapse at each profile point is exp(phi_shifted).

**Required outputs** (see `TovResult` in `types.rs`):

- `total_mass`:  M = m(R)
- `stellar_radius`:  R
- `central_pressure`:  P_c
- `compactness`:  2 M / R
- `surface_redshift`:  (1 - 2M/R)^{-1/2} - 1
- `baryon_mass`:  integral of 4 pi r^2 rho_0 / sqrt(1 - 2m/r) dr from 0 to R
- `profile`:  50 evenly-spaced radial points from r_start to 0.999 R, each with
  (r, pressure, enclosed_mass, lapse).

### Phase 2 --- Oppenheimer-Snyder Collapse

Integrate the Friedmann equation for a collapsing uniform-density dust ball:

    (da/dtau)^2 = (2 M / R_b^3) (1/a - 1)

where a(tau) is the scale factor, tau is proper time of a comoving observer, M
is the total mass, and R_b is the initial areal radius.

**Initial conditions:**  a(0) = 1,  da/dtau(0) = 0  (collapse from rest).

**Surface radius:**  r_surface(tau) = R_b * a(tau).

**Horizon crossing:**  The surface crosses the Schwarzschild radius when
r_surface = 2 M  (i.e. a = 2 M / R_b).

**Singularity:**  a -> 0.

**Required outputs** (see `CollapseResult` in `types.rs`):

- `tau_singularity`:  proper time when a reaches zero.
- `tau_horizon`:  proper time when r_surface = 2 M.
- `horizon_radius`:  2 M.
- `trajectory`:  51 points from tau = 0 to tau = tau_singularity (inclusive),
  each with (tau, r_surface, scale_factor, energy).
  The Friedmann energy is E = 0.5 (da/dtau)^2 - M / (R_b^3 a).
- `energy_drift_max`:  max |E(tau) - E(0)| over the trajectory.

## Verification

Run the visible tests:

    python3 -m pytest /app/files/tests.py -v

Do **not** run tests directly with `python3 tests.py` --- they require pytest.

## Constraints

- Work entirely offline inside the container.
- All outputs must be deterministic (no threading non-determinism, no HashMap
  iteration order).
- Do not modify test or verifier files.
- Do not add any crate dependencies beyond serde, serde_json, and clap.
