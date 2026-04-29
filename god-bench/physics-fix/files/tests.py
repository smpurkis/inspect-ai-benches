"""
Visible tests for the GR collapse simulator.

All expected values are derived in-test from closed-form GR formulas, not from
shipped reference JSONs.  The agent must produce physically-correct output.

Sources used by these tests:
  - TOV equations:                   Tolman 1939, Phys. Rev. 55, 364;
                                     Oppenheimer & Volkoff 1939, Phys. Rev. 55, 374.
  - Schwarzschild interior solution: Schwarzschild 1916, Sitzungsber. Preuss. Akad. Wiss.
  - Oppenheimer-Snyder cycloid:      Oppenheimer & Snyder 1939, Phys. Rev. 56, 455.
"""

import json
import math
import os
import subprocess

import numpy as np

BINARY = "/app/target/release/gr_sim"
FIXTURES = "/app/files/fixtures"


def _build():
    return subprocess.run(
        ["cargo", "build", "--release"],
        capture_output=True, text=True, cwd="/app", timeout=300,
    )


def _run_sim(seed_file):
    return subprocess.run(
        [BINARY, "--input", seed_file],
        capture_output=True, text=True, timeout=120,
    )


def _load_seed(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def _run_seed(name):
    """Build, run the binary on the named seed, return parsed output dict."""
    result = _build()
    assert result.returncode == 0, f"cargo build failed:\n{result.stderr[-2000:]}"
    seed_path = os.path.join(FIXTURES, name)
    r = _run_sim(seed_path)
    assert r.returncode == 0, (
        f"Simulator crashed on {name}:\n"
        f"stdout={r.stdout[:500]}\nstderr={r.stderr[:500]}"
    )
    return json.loads(r.stdout)


# ------------------------------------------------------------------
# V1. Build
# ------------------------------------------------------------------

def test_builds():
    """cargo build --release succeeds."""
    result = _build()
    assert result.returncode == 0, f"cargo build failed:\n{result.stderr[-3000:]}"


# ------------------------------------------------------------------
# V2-V7. TOV checks (uniform density)
# ------------------------------------------------------------------

def _schwarzschild_pressure(rho_0, M, R, r):
    """Closed-form interior Schwarzschild pressure (Schwarzschild 1916)
    for a uniform-density (incompressible) star.

        P(r) / rho_0 = (sqrt(1 - 2M r^2/R^3) - sqrt(1-2M/R))
                       / (3 sqrt(1-2M/R) - sqrt(1 - 2M r^2/R^3))

    Reference: K. Schwarzschild, Sitzungsberichte der Königlich Preussischen
    Akademie der Wissenschaften zu Berlin (1916), p. 424.
    """
    C = 2.0 * M / R
    inner = math.sqrt(max(1.0 - C * (r * r) / (R * R), 0.0))
    outer = math.sqrt(max(1.0 - C, 0.0))
    denom = 3.0 * outer - inner
    return rho_0 * (inner - outer) / denom


def test_tov_uniform_total_mass():
    """M reported by sim must equal (4 pi / 3) rho_0 R^3 (TOV with uniform density).

    Source: Tolman-Oppenheimer-Volkoff equation, dm/dr = 4 pi r^2 rho.
    """
    seed = _load_seed("seed_tov_uniform.json")["tov"]
    rho_0 = seed["central_density"]

    out = _run_seed("seed_tov_uniform.json")["tov"]
    M = out["total_mass"]
    R = out["stellar_radius"]

    expected_M = (4.0 / 3.0) * math.pi * rho_0 * R**3
    np.testing.assert_allclose(
        M, expected_M, rtol=1e-3,
        err_msg=f"Total mass {M} not consistent with uniform density: "
                f"(4/3) pi rho_0 R^3 = {expected_M}",
    )


def test_tov_uniform_pressure_profile_schwarzschild_1916():
    """Pressure at 5 inner profile points must match the closed-form
    Schwarzschild 1916 interior pressure.
    """
    seed = _load_seed("seed_tov_uniform.json")["tov"]
    rho_0 = seed["central_density"]

    out = _run_seed("seed_tov_uniform.json")["tov"]
    M = out["total_mass"]
    R = out["stellar_radius"]
    profile = out["profile"]
    assert len(profile) == 50, f"profile length {len(profile)} != 50"

    # Pick 5 evenly-spaced indices excluding the very ends (avoid r=0 / r=R).
    indices = [5, 15, 25, 35, 45]
    for idx in indices:
        pt = profile[idx]
        r = pt["r"]
        P_actual = pt["pressure"]
        P_expected = _schwarzschild_pressure(rho_0, M, R, r)
        np.testing.assert_allclose(
            P_actual, P_expected,
            atol=1e-6, rtol=5e-3,
            err_msg=f"P(r={r:.4f}) = {P_actual:.6e}, "
                    f"Schwarzschild 1916 closed form = {P_expected:.6e}",
        )


def test_tov_surface_lapse_matching():
    """Lapse at the outermost profile point must satisfy the Schwarzschild
    matching condition: lapse(R) = sqrt(1 - 2M/R).

    Source: Israel matching (lapse continuity) at the stellar surface.
    """
    out = _run_seed("seed_tov_uniform.json")["tov"]
    M = out["total_mass"]
    R = out["stellar_radius"]
    lapse_at_surface = out["profile"][-1]["lapse"]
    expected = math.sqrt(1.0 - 2.0 * M / R)
    np.testing.assert_allclose(
        lapse_at_surface, expected,
        atol=2e-4,
        err_msg=f"surface lapse {lapse_at_surface} != sqrt(1-2M/R)={expected}",
    )


def test_tov_pressure_monotone_nonincreasing():
    """Pressure profile must be non-increasing in r (TOV gives dP/dr <= 0)."""
    out = _run_seed("seed_tov_uniform.json")["tov"]
    profile = out["profile"]
    pressures = [pt["pressure"] for pt in profile]
    for i in range(len(pressures) - 1):
        assert pressures[i + 1] <= pressures[i] + 1e-10, (
            f"Pressure increased between profile[{i}]={pressures[i]} "
            f"and profile[{i+1}]={pressures[i+1]}"
        )


def test_tov_central_pressure_positive():
    """central_pressure, total_mass, stellar_radius must all be positive."""
    out = _run_seed("seed_tov_uniform.json")["tov"]
    assert out["central_pressure"] > 0, f"P_c={out['central_pressure']} <= 0"
    assert out["total_mass"] > 0, f"M={out['total_mass']} <= 0"
    assert out["stellar_radius"] > 0, f"R={out['stellar_radius']} <= 0"
    assert 0 < out["compactness"] < 8.0 / 9.0, (
        f"compactness {out['compactness']} outside (0, 8/9) Buchdahl bound"
    )


def test_tov_no_nan_in_profile():
    """Every profile point has finite r/pressure/enclosed_mass/lapse."""
    out = _run_seed("seed_tov_uniform.json")["tov"]
    for i, pt in enumerate(out["profile"]):
        for key in ("r", "pressure", "enclosed_mass", "lapse"):
            v = pt[key]
            assert math.isfinite(v), f"profile[{i}].{key} = {v} (not finite)"


# ------------------------------------------------------------------
# V8-V12. Oppenheimer-Snyder collapse checks
# ------------------------------------------------------------------

def _cycloid_eta_h(M, R_b):
    """Conformal time eta_H at horizon crossing (a = 2M/R_b)."""
    cos_eta = 4.0 * M / R_b - 1.0
    if cos_eta >= 1.0:
        return 0.0
    if cos_eta <= -1.0:
        return math.pi
    return math.acos(cos_eta)


def test_os_cycloid_singularity_time():
    """tau_singularity = pi * sqrt(R_b^3 / (8M)).

    Source: Oppenheimer & Snyder 1939 (cycloid solution to the Friedmann
    equation for collapsing uniform-density dust).
    """
    seed = _load_seed("seed_os_standard.json")["collapse"]
    M, R_b = seed["mass"], seed["initial_radius"]
    out = _run_seed("seed_os_standard.json")["collapse"]
    expected = math.pi * math.sqrt(R_b**3 / (8.0 * M))
    np.testing.assert_allclose(
        out["tau_singularity"], expected, rtol=1e-4,
        err_msg=f"tau_sing {out['tau_singularity']} != cycloid pi*sqrt(R_b^3/8M)={expected}",
    )


def test_os_cycloid_horizon_time():
    """tau_horizon and horizon_radius from analytical cycloid.

    eta_H = arccos(4M/R_b - 1)
    tau_H = sqrt(R_b^3/(8M)) * (eta_H + sin eta_H)
    horizon_radius = 2M.
    """
    seed = _load_seed("seed_os_standard.json")["collapse"]
    M, R_b = seed["mass"], seed["initial_radius"]
    out = _run_seed("seed_os_standard.json")["collapse"]

    eta_H = _cycloid_eta_h(M, R_b)
    expected_tau_H = math.sqrt(R_b**3 / (8.0 * M)) * (eta_H + math.sin(eta_H))

    np.testing.assert_allclose(
        out["tau_horizon"], expected_tau_H, rtol=1e-3,
        err_msg=f"tau_H {out['tau_horizon']} != cycloid {expected_tau_H}",
    )
    np.testing.assert_allclose(
        out["horizon_radius"], 2.0 * M, atol=1e-5,
        err_msg=f"horizon_radius {out['horizon_radius']} != 2M={2*M}",
    )


def test_os_initial_conditions():
    """First trajectory point: a=1, r_surface=R_b, energy = -M/R_b^3."""
    seed = _load_seed("seed_os_standard.json")["collapse"]
    M, R_b = seed["mass"], seed["initial_radius"]
    out = _run_seed("seed_os_standard.json")["collapse"]
    p0 = out["trajectory"][0]
    np.testing.assert_allclose(p0["scale_factor"], 1.0, atol=1e-6,
                               err_msg=f"a(0)={p0['scale_factor']} != 1")
    np.testing.assert_allclose(p0["r_surface"], R_b, atol=1e-6,
                               err_msg=f"r_surf(0)={p0['r_surface']} != R_b={R_b}")
    expected_E0 = -M / R_b**3
    np.testing.assert_allclose(p0["energy"], expected_E0, atol=1e-9,
                               err_msg=f"E(0)={p0['energy']} != -M/R_b^3={expected_E0}")


def test_os_trajectory_monotone_decreasing_r():
    """r_surface must monotonically decrease (collapse from rest); final
    scale factor ~ 0."""
    out = _run_seed("seed_os_standard.json")["collapse"]
    traj = out["trajectory"]
    rs = [pt["r_surface"] for pt in traj]
    for i in range(len(rs) - 1):
        assert rs[i + 1] <= rs[i] + 1e-10, (
            f"r_surface increased between traj[{i}]={rs[i]} and traj[{i+1}]={rs[i+1]}"
        )
    assert traj[-1]["scale_factor"] <= 1e-3, (
        f"final scale_factor {traj[-1]['scale_factor']} not near 0"
    )


def test_os_energy_conservation_all_points():
    """|E(tau_i) - E(0)| must be < 1e-7 for every trajectory point.
    Stronger than the simulator's reported energy_drift_max (single value).
    """
    out = _run_seed("seed_os_standard.json")["collapse"]
    traj = out["trajectory"]
    E0 = traj[0]["energy"]
    drifts = [abs(pt["energy"] - E0) for pt in traj
              if pt["scale_factor"] > 1e-12]
    max_drift = max(drifts)
    assert max_drift < 1e-7, (
        f"max energy drift {max_drift:.3e} >= 1e-7"
    )


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(["python3", "-m", "pytest", __file__, "-v"])
    )
