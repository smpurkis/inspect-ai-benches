use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// Input (seed JSON)
// ---------------------------------------------------------------------------

/// Top-level simulation configuration read from the seed JSON file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimConfig {
    /// Which simulation to run: "tov", "collapse", or "both".
    pub mode: String,

    /// TOV configuration (present when mode is "tov" or "both").
    #[serde(default)]
    pub tov: Option<TovConfig>,

    /// Collapse configuration (present when mode is "collapse" or "both").
    #[serde(default)]
    pub collapse: Option<CollapseConfig>,
}

/// Configuration for the TOV (stellar equilibrium) solver.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TovConfig {
    /// Central rest-mass density rho_0(r=0).
    pub central_density: f64,

    /// Central pressure (used only for uniform-density stars).
    #[serde(default)]
    pub central_pressure: Option<f64>,

    /// Polytropic constant K in  P = K * rho_0^Gamma.
    /// Set to 0.0 (or omit) for uniform-density mode.
    #[serde(default)]
    pub eos_k: f64,

    /// Polytropic exponent Gamma.
    #[serde(default)]
    pub eos_gamma: f64,

    /// If true, use constant (uniform) energy density throughout the star.
    #[serde(default)]
    pub uniform_density: bool,

    /// Starting radius for the integration (small offset to avoid r=0 singularity).
    #[serde(default = "default_r_start")]
    pub r_start: f64,

    /// Initial radial step size.
    #[serde(default = "default_dr_initial")]
    pub dr_initial: f64,

    /// Relative tolerance for the ODE integrator.
    #[serde(default = "default_rtol")]
    pub rtol: f64,

    /// Absolute tolerance for the ODE integrator.
    #[serde(default = "default_atol")]
    pub atol: f64,
}

/// Configuration for the Oppenheimer-Snyder collapse solver.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CollapseConfig {
    /// Total gravitational mass of the dust ball (geometric units).
    pub mass: f64,

    /// Initial areal radius of the dust-ball surface.
    pub initial_radius: f64,

    /// Number of integration steps.
    #[serde(default = "default_num_steps")]
    pub num_steps: usize,

    /// Relative tolerance for the ODE integrator.
    #[serde(default = "default_rtol")]
    pub rtol: f64,

    /// Absolute tolerance for the ODE integrator.
    #[serde(default = "default_atol")]
    pub atol: f64,
}

// Default helpers -------------------------------------------------------

fn default_r_start() -> f64 {
    1e-6
}
fn default_dr_initial() -> f64 {
    0.01
}
fn default_rtol() -> f64 {
    1e-10
}
fn default_atol() -> f64 {
    1e-12
}
fn default_num_steps() -> usize {
    10_000
}

// ---------------------------------------------------------------------------
// Output (result JSON)
// ---------------------------------------------------------------------------

/// Complete simulation output.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimOutput {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tov: Option<TovResult>,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub collapse: Option<CollapseResult>,
}

/// Result of TOV integration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TovResult {
    /// Total gravitational mass M.
    pub total_mass: f64,

    /// Stellar radius R (where P=0).
    pub stellar_radius: f64,

    /// Central pressure P(r=0).
    pub central_pressure: f64,

    /// Compactness parameter 2M/R.
    pub compactness: f64,

    /// Surface gravitational redshift z = (1-2M/R)^{-1/2} - 1.
    pub surface_redshift: f64,

    /// Baryon (rest) mass: integral of rho_0 dV_proper.
    pub baryon_mass: f64,

    /// Radial profile at evenly-spaced points.
    pub profile: Vec<TovProfilePoint>,
}

/// One point in the TOV radial profile.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TovProfilePoint {
    /// Areal radius.
    pub r: f64,
    /// Pressure.
    pub pressure: f64,
    /// Enclosed gravitational mass m(r).
    pub enclosed_mass: f64,
    /// Metric lapse function exp(phi).
    pub lapse: f64,
}

/// Result of Oppenheimer-Snyder collapse integration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CollapseResult {
    /// Proper time at singularity (a -> 0).
    pub tau_singularity: f64,

    /// Proper time at horizon crossing (r_surface = 2M).
    pub tau_horizon: f64,

    /// Horizon radius = 2M.
    pub horizon_radius: f64,

    /// Collapse trajectory.
    pub trajectory: Vec<CollapseTrajectoryPoint>,

    /// Maximum |E(tau) - E(0)| over the trajectory.
    pub energy_drift_max: f64,
}

/// One point along the collapse trajectory.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CollapseTrajectoryPoint {
    /// Proper time.
    pub tau: f64,
    /// Surface areal radius R_b * a(tau).
    pub r_surface: f64,
    /// Scale factor a(tau).
    pub scale_factor: f64,
    /// Friedmann energy: 0.5*(da/dtau)^2 - M/(R_b^3 * a).
    pub energy: f64,
}

// ---------------------------------------------------------------------------
// Internal ODE states (not serialised, used by lib.rs)
// ---------------------------------------------------------------------------

/// Internal state for the TOV integrator.
#[derive(Debug, Clone, Copy)]
pub struct TovState {
    /// Pressure.
    pub p: f64,
    /// Enclosed mass.
    pub m: f64,
    /// Metric potential phi.
    pub phi: f64,
}

/// Internal state for the collapse integrator.
#[derive(Debug, Clone, Copy)]
pub struct CollapseState {
    /// Scale factor a.
    pub a: f64,
    /// da/dtau.
    pub da_dtau: f64,
}
