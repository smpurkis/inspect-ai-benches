pub mod types;

use types::*;

// ===================================================================
// TOV Solver
// ===================================================================

/// Solve the Tolman-Oppenheimer-Volkoff equations for a static,
/// spherically symmetric star in hydrostatic equilibrium.
///
/// The three coupled ODEs (in geometric units G = c = 1) are:
///
///   dm/dr   = 4 pi r^2 rho
///   dP/dr   = -(rho + P)(m + 4 pi r^3 P) / [r (r - 2m)]
///   dphi/dr = (m + 4 pi r^3 P) / [r (r - 2m)]
///
/// For a polytropic EOS:  P = K rho_0^Gamma,
///                        rho = rho_0 + P / (Gamma - 1).
///
/// For uniform density:   rho = central_density (constant),
///                        P_c given in config.
///
/// Integration starts at r_start (small offset) and proceeds outward
/// until P <= 0 (stellar surface).  The surface is found by
/// interpolation.
///
/// Returns a `TovResult` with global quantities and a radial profile.
pub fn solve_tov(config: &TovConfig) -> TovResult {
    todo!("Implement the TOV solver")
}

// ===================================================================
// Oppenheimer-Snyder Collapse
// ===================================================================

/// Simulate the Oppenheimer-Snyder collapse of a uniform-density dust
/// ball.
///
/// The Friedmann equation for the scale factor a(tau) is:
///
///   (da/dtau)^2 = (2 M / R_b^3) (1/a - 1)
///
/// with initial conditions a(0) = 1, da/dtau(0) = 0 (collapse from
/// rest at areal radius R_b).
///
/// The surface radius is r_surface(tau) = R_b * a(tau).
/// Horizon crossing occurs when r_surface = 2 M.
/// Singularity is reached when a -> 0.
///
/// The trajectory, horizon-crossing time, and singularity time must
/// all be computed numerically.
///
/// Returns a `CollapseResult`.
pub fn os_collapse(config: &CollapseConfig) -> CollapseResult {
    todo!("Implement the Oppenheimer-Snyder collapse solver")
}

// ===================================================================
// Helper stubs — you may use, modify, or delete these.
// ===================================================================

/// Compute pressure and energy density from the polytropic EOS.
///
///   P   = K * rho_0^Gamma
///   rho = rho_0 + P / (Gamma - 1)
///
/// Returns (P, rho).
pub fn polytropic_eos(rho_0: f64, k: f64, gamma: f64) -> (f64, f64) {
    todo!("Implement polytropic equation of state")
}

/// Perform one step of the RK45 (Dormand-Prince) adaptive integrator.
///
/// Given state y at independent variable t, advance by step h.
/// Returns (y_new, error_estimate).
///
/// You must implement the Butcher tableau yourself — no external ODE
/// crate is allowed.
pub fn rk45_step<F>(
    f: &F,
    t: f64,
    y: &[f64],
    h: f64,
) -> (Vec<f64>, f64)
where
    F: Fn(f64, &[f64]) -> Vec<f64>,
{
    todo!("Implement RK45 adaptive step")
}
