#!/usr/bin/env python3
"""
Generate seed and reference fixture files for the GR collapse benchmark.

Produces:
  - TOV seeds + references (uniform density, polytrope, high compactness)
  - Oppenheimer-Snyder collapse seeds + references (standard, compact, marginal)

All quantities in geometric units: G = c = 1.
"""

import json
import math
import os

import numpy as np
from scipy.integrate import solve_ivp, quad
from scipy.optimize import brentq


# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
FILES_FIXTURES = os.path.join(BASE_DIR, "files", "fixtures")
HIDDEN_FIXTURES = os.path.join(BASE_DIR, "hidden", "fixtures")

os.makedirs(FILES_FIXTURES, exist_ok=True)
os.makedirs(HIDDEN_FIXTURES, exist_ok=True)


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)
    print(f"  wrote {path}")


# ===================================================================
# TOV solver  (Tolman-Oppenheimer-Volkoff)
# ===================================================================

def _pressure_event():
    """Event that fires when P crosses zero (star surface)."""
    def event(r, y, *args):
        return y[0]
    event.terminal = True
    event.direction = -1
    return event


def tov_rhs_polytrope(r, y, K, Gamma):
    """RHS for TOV with polytropic EOS: P = K * rho_0^Gamma.
    State y = [P, m, phi].
    """
    P, m, phi = y
    if P <= 0.0:
        return [0.0, 0.0, 0.0]

    rho_0 = (P / K) ** (1.0 / Gamma)
    rho = rho_0 + P / (Gamma - 1.0)

    denom = r * (r - 2.0 * m)
    if abs(denom) < 1e-50:
        return [0.0, 0.0, 0.0]

    dP_dr = -(rho + P) * (m + 4.0 * math.pi * r**3 * P) / denom
    dm_dr = 4.0 * math.pi * r**2 * rho
    dphi_dr = (m + 4.0 * math.pi * r**3 * P) / denom

    return [dP_dr, dm_dr, dphi_dr]


def tov_rhs_uniform(r, y, rho_0_const):
    """RHS for TOV with uniform (constant) energy density.
    State y = [P, m, phi].
    """
    P, m, phi = y
    if P <= 0.0:
        return [0.0, 0.0, 0.0]

    rho = rho_0_const

    denom = r * (r - 2.0 * m)
    if abs(denom) < 1e-50:
        return [0.0, 0.0, 0.0]

    dP_dr = -(rho + P) * (m + 4.0 * math.pi * r**3 * P) / denom
    dm_dr = 4.0 * math.pi * r**2 * rho
    dphi_dr = (m + 4.0 * math.pi * r**3 * P) / denom

    return [dP_dr, dm_dr, dphi_dr]


def _build_profile_and_baryon(sol, R_star, compactness, K, Gamma, is_uniform,
                              rho_0_const, r_start, n_profile=50):
    """Build radial profile and compute baryon mass from TOV solution."""
    phi_surface = 0.5 * math.log(1.0 - compactness) if compactness < 1.0 else float('nan')

    r_end = R_star * 0.999
    r_profile = np.linspace(r_start, r_end, n_profile)
    raw = []
    for r_val in r_profile:
        state = sol.sol(float(r_val))
        raw.append((float(r_val), max(float(state[0]), 0.0),
                     float(state[1]), float(state[2])))

    phi_at_end = float(sol.sol(r_end)[2])
    phi_shift = phi_surface - phi_at_end

    profile = []
    for r_val, P_val, m_val, phi_val in raw:
        lapse = math.exp(phi_val + phi_shift)
        profile.append({
            "r": round(r_val, 12),
            "pressure": round(P_val, 14),
            "enclosed_mass": round(m_val, 12),
            "lapse": round(lapse, 12),
        })

    # Baryon mass
    def baryon_integrand(r_val):
        state = sol.sol(r_val)
        P_val = max(state[0], 0.0)
        m_val = state[1]
        if P_val <= 0:
            return 0.0
        if is_uniform:
            rho0 = rho_0_const
        else:
            rho0 = (P_val / K) ** (1.0 / Gamma)
        factor = 1.0 - 2.0 * m_val / r_val
        if factor <= 0:
            return 0.0
        return 4.0 * math.pi * r_val**2 * rho0 / math.sqrt(factor)

    baryon_mass, _ = quad(baryon_integrand, r_start, r_end,
                          limit=200, epsrel=1e-12)

    return profile, float(baryon_mass)


def solve_tov_polytrope(rho_c, K, Gamma, r_start=1e-6, r_max=500.0,
                        rtol=1e-12, atol=1e-14, dr_max=0.1):
    """Solve TOV for a polytropic EOS.  Returns reference dict."""
    P_c = K * rho_c ** Gamma
    rho_c_energy = rho_c + P_c / (Gamma - 1.0)

    m0 = (4.0 / 3.0) * math.pi * rho_c_energy * r_start**3
    y0 = [P_c, m0, 0.0]

    sol = solve_ivp(
        tov_rhs_polytrope, [r_start, r_max], y0,
        args=(K, Gamma),
        method='RK45', rtol=rtol, atol=atol,
        events=_pressure_event(),
        dense_output=True, max_step=dr_max,
    )

    if sol.t_events[0].size > 0:
        R_star = float(sol.t_events[0][0])
    else:
        idx = np.argmax(sol.y[0] <= 0)
        R_star = float(sol.t[idx]) if idx > 0 else float(sol.t[-1])

    M_total = float(sol.sol(R_star)[1])
    compactness = 2.0 * M_total / R_star
    surface_redshift = (1.0 / math.sqrt(1.0 - compactness) - 1.0
                        if compactness < 1.0 else float('inf'))

    profile, baryon_mass = _build_profile_and_baryon(
        sol, R_star, compactness, K, Gamma,
        is_uniform=False, rho_0_const=0.0, r_start=r_start)

    return {
        "total_mass": round(M_total, 12),
        "stellar_radius": round(R_star, 12),
        "central_pressure": round(P_c, 12),
        "compactness": round(compactness, 12),
        "surface_redshift": round(surface_redshift, 12),
        "baryon_mass": round(baryon_mass, 12),
        "profile": profile,
    }


def solve_tov_uniform(rho_0, P_c, r_start=1e-6, r_max=500.0,
                      rtol=1e-12, atol=1e-14, dr_max=0.1):
    """Solve TOV for uniform (incompressible) density.  P_c given directly."""
    m0 = (4.0 / 3.0) * math.pi * rho_0 * r_start**3
    y0 = [P_c, m0, 0.0]

    sol = solve_ivp(
        tov_rhs_uniform, [r_start, r_max], y0,
        args=(rho_0,),
        method='RK45', rtol=rtol, atol=atol,
        events=_pressure_event(),
        dense_output=True, max_step=dr_max,
    )

    if sol.t_events[0].size > 0:
        R_star = float(sol.t_events[0][0])
    else:
        idx = np.argmax(sol.y[0] <= 0)
        R_star = float(sol.t[idx]) if idx > 0 else float(sol.t[-1])

    M_total = (4.0 / 3.0) * math.pi * rho_0 * R_star**3
    compactness = 2.0 * M_total / R_star
    surface_redshift = (1.0 / math.sqrt(1.0 - compactness) - 1.0
                        if compactness < 1.0 else float('inf'))

    profile, baryon_mass = _build_profile_and_baryon(
        sol, R_star, compactness, K=0, Gamma=0,
        is_uniform=True, rho_0_const=rho_0, r_start=r_start)

    return {
        "total_mass": round(M_total, 12),
        "stellar_radius": round(R_star, 12),
        "central_pressure": round(P_c, 12),
        "compactness": round(compactness, 12),
        "surface_redshift": round(surface_redshift, 12),
        "baryon_mass": round(baryon_mass, 12),
        "profile": profile,
    }


# ===================================================================
# Oppenheimer-Snyder collapse (analytical cycloid solution)
# ===================================================================

def os_collapse_analytical(M, R_b, num_trajectory_points=50):
    """Compute OS collapse quantities analytically.

    Dust ball of mass M starting at areal radius R_b, collapsing from rest.
    Friedmann equation: (da/dtau)^2 = (2M / R_b^3) * (1/a - 1)
    Parametric: a = (1 + cos eta)/2,  tau = sqrt(R_b^3/(8M)) * (eta + sin eta)
    """
    tau_factor = math.sqrt(R_b**3 / (8.0 * M))

    # Singularity: eta = pi
    tau_singularity = tau_factor * math.pi

    # Horizon crossing: r_surface = R_b * a = 2M  =>  a_H = 2M/R_b
    a_H = 2.0 * M / R_b
    cos_eta_H = 4.0 * M / R_b - 1.0

    if cos_eta_H > 1.0:
        # Already inside horizon at start
        eta_H = 0.0
        tau_H = 0.0
    elif cos_eta_H < -1.0:
        eta_H = math.pi
        tau_H = tau_singularity
    else:
        eta_H = math.acos(cos_eta_H)
        tau_H = tau_factor * (eta_H + math.sin(eta_H))

    horizon_radius = 2.0 * M

    # Trajectory: eta from 0 to pi inclusive
    trajectory = []
    eta_values = np.linspace(0, math.pi, num_trajectory_points + 1)
    E_expected = -M / R_b**3   # Friedmann energy constant
    for eta in eta_values:
        a = (1.0 + math.cos(eta)) / 2.0
        tau = tau_factor * (eta + math.sin(eta))
        r_surface = R_b * a

        if a > 1e-15:
            da_dtau_sq = (2.0 * M / R_b**3) * (1.0 / a - 1.0)
            E_actual = 0.5 * da_dtau_sq - M / (R_b**3 * a)
        else:
            E_actual = E_expected

        trajectory.append({
            "tau": round(float(tau), 12),
            "r_surface": round(float(r_surface), 12),
            "scale_factor": round(float(a), 12),
            "energy": round(float(E_actual), 12),
        })

    energy_drift_max = max(
        abs(pt["energy"] - E_expected) for pt in trajectory
        if abs(pt["scale_factor"]) > 1e-15
    )

    return {
        "tau_singularity": round(tau_singularity, 12),
        "tau_horizon": round(tau_H, 12),
        "horizon_radius": round(horizon_radius, 12),
        "trajectory": trajectory,
        "energy_drift_max": round(energy_drift_max, 12),
    }


# ===================================================================
# Generate all fixtures
# ===================================================================

def gen_tov_uniform():
    """TOV with uniform density rho_0 = 1e-4, P_c = 1e-5 (moderate compactness)."""
    print("Generating TOV uniform density fixtures...")
    rho_0 = 1e-4
    P_c = 1e-5       # gives a moderate-compactness star

    seed = {
        "mode": "tov",
        "tov": {
            "central_density": rho_0,
            "central_pressure": P_c,
            "eos_k": 0.0,
            "eos_gamma": 0.0,
            "uniform_density": True,
            "r_start": 1e-6,
            "dr_initial": 0.01,
            "rtol": 1e-10,
            "atol": 1e-12,
        }
    }

    ref_data = {"tov": solve_tov_uniform(rho_0, P_c)}

    write_json(os.path.join(FILES_FIXTURES, "seed_tov_uniform.json"), seed)
    write_json(os.path.join(FILES_FIXTURES, "reference_tov_uniform.json"), ref_data)
    write_json(os.path.join(HIDDEN_FIXTURES, "seed_tov_uniform.json"), seed)
    write_json(os.path.join(HIDDEN_FIXTURES, "reference_tov_uniform.json"), ref_data)

    t = ref_data["tov"]
    print(f"  M={t['total_mass']:.6e}, R={t['stellar_radius']:.4f}, "
          f"C={t['compactness']:.6f}")


def gen_tov_polytrope():
    """TOV with polytropic EOS: K=100, Gamma=2, rho_c=1.28e-3."""
    print("Generating TOV polytrope fixtures...")
    K, Gamma, rho_c = 100.0, 2.0, 1.28e-3

    seed = {
        "mode": "tov",
        "tov": {
            "central_density": rho_c,
            "eos_k": K,
            "eos_gamma": Gamma,
            "uniform_density": False,
            "r_start": 1e-6,
            "dr_initial": 0.01,
            "rtol": 1e-10,
            "atol": 1e-12,
        }
    }

    ref_data = {"tov": solve_tov_polytrope(rho_c, K, Gamma)}

    write_json(os.path.join(HIDDEN_FIXTURES, "seed_tov_polytrope.json"), seed)
    write_json(os.path.join(HIDDEN_FIXTURES, "reference_tov_polytrope.json"), ref_data)

    t = ref_data["tov"]
    print(f"  M={t['total_mass']:.6e}, R={t['stellar_radius']:.4f}, "
          f"C={t['compactness']:.6f}")


def gen_tov_high_compactness():
    """TOV with high compactness 2M/R ~ 0.7 (near Buchdahl limit).
    Uses uniform density (incompressible fluid) which can reach high C."""
    print("Generating TOV high-compactness fixtures...")
    rho_0 = 1e-4
    target = 0.7

    def residual(log_Pc):
        P_c = math.exp(log_Pc)
        r = solve_tov_uniform(rho_0, P_c)
        return r["compactness"] - target

    # C=0.284 at P_c=1e-5, C=0.75 at P_c=1e-4
    log_Pc = brentq(residual, math.log(1e-5), math.log(1e-4),
                    xtol=1e-12, rtol=1e-12)
    P_c = math.exp(log_Pc)

    seed = {
        "mode": "tov",
        "tov": {
            "central_density": rho_0,
            "central_pressure": P_c,
            "eos_k": 0.0,
            "eos_gamma": 0.0,
            "uniform_density": True,
            "r_start": 1e-6,
            "dr_initial": 0.001,
            "rtol": 1e-10,
            "atol": 1e-12,
        }
    }

    ref_data = {"tov": solve_tov_uniform(rho_0, P_c)}

    write_json(os.path.join(HIDDEN_FIXTURES, "seed_tov_high_compactness.json"), seed)
    write_json(os.path.join(HIDDEN_FIXTURES, "reference_tov_high_compactness.json"), ref_data)

    t = ref_data["tov"]
    print(f"  P_c={P_c:.6e}, M={t['total_mass']:.6e}, "
          f"R={t['stellar_radius']:.4f}, C={t['compactness']:.6f}")


def gen_os(name, M, R_b, dirs):
    """Generate OS collapse seed + reference."""
    print(f"Generating OS collapse '{name}' fixtures...")
    seed = {
        "mode": "collapse",
        "collapse": {
            "mass": M,
            "initial_radius": R_b,
            "num_steps": 10000,
            "rtol": 1e-10,
            "atol": 1e-12,
        }
    }
    ref_data = {"collapse": os_collapse_analytical(M, R_b)}

    for d in dirs:
        write_json(os.path.join(d, f"seed_os_{name}.json"), seed)
        write_json(os.path.join(d, f"reference_os_{name}.json"), ref_data)

    c = ref_data["collapse"]
    print(f"  tau_sing={c['tau_singularity']:.6f}, tau_H={c['tau_horizon']:.6f}")


def main():
    print("=" * 60)
    print("Generating GR collapse benchmark fixtures")
    print("=" * 60)

    gen_tov_uniform()
    gen_tov_polytrope()
    gen_tov_high_compactness()

    # Visible + hidden
    gen_os("standard", M=1.0, R_b=10.0, dirs=[FILES_FIXTURES, HIDDEN_FIXTURES])
    # Hidden only
    gen_os("compact", M=0.5, R_b=5.0, dirs=[HIDDEN_FIXTURES])
    gen_os("marginal", M=1.0, R_b=2.5, dirs=[HIDDEN_FIXTURES])

    print("=" * 60)
    print("All fixtures generated successfully.")


if __name__ == "__main__":
    main()
