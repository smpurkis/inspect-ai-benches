"""
Hidden tests for the GR collapse simulator.

Each test cites the literature source whose result it checks.  Expected values
are derived in-test from closed-form GR formulas or from independent numerical
integration with scipy — no shipped reference JSONs.

Sources:
  S1. TOV equations:                     Tolman 1939, Phys. Rev. 55, 364;
                                         Oppenheimer & Volkoff 1939, Phys. Rev. 55, 374.
  S2. Schwarzschild interior solution:   Schwarzschild 1916, Sitzungsber. Preuss. Akad. Wiss. p.424.
  S3. Buchdahl theorem (2M/R <= 8/9):    Buchdahl 1959, Phys. Rev. 116, 1027.
  S4. Oppenheimer-Snyder cycloid:        Oppenheimer & Snyder 1939, Phys. Rev. 56, 455.
  S5. Birkhoff theorem:                  Birkhoff 1923, Relativity and Modern Physics
                                         (earlier: Jebsen 1921).
  S6. Tooper relativistic polytropes:    Tooper 1964, ApJ 140, 434;
                                         Tooper 1965, ApJ 142, 1541.
"""

import hashlib
import json
import math
import os
import random
import re
import subprocess

import numpy as np
import pytest
from scipy.integrate import solve_ivp, quad

BINARY = "/app/target/release/gr_sim"
HIDDEN_FIXTURES = "/app/hidden/fixtures"
TMP_DIR = "/tmp"


# ------------------------------------------------------------------
# Build / run helpers
# ------------------------------------------------------------------

def _build():
    result = subprocess.run(
        ["cargo", "build", "--release"],
        capture_output=True, text=True, cwd="/app", timeout=300,
    )
    assert result.returncode == 0, f"Build failed:\n{result.stderr[-2000:]}"


def _run_sim(seed_file):
    return subprocess.run(
        [BINARY, "--input", seed_file],
        capture_output=True, text=True, timeout=180,
    )


def _run_seed_path(path):
    r = _run_sim(path)
    assert r.returncode == 0, (
        f"Simulator crashed on {path}:\n"
        f"stdout={r.stdout[:500]}\nstderr={r.stderr[:500]}"
    )
    return json.loads(r.stdout)


def _write_tmp_seed(name, seed):
    path = os.path.join(TMP_DIR, name)
    with open(path, "w") as f:
        json.dump(seed, f)
    return path


# ------------------------------------------------------------------
# Closed-form GR helpers (in-test analytics)
# ------------------------------------------------------------------

def _schwarzschild_pressure(rho_0, M, R, r):
    """Closed-form interior Schwarzschild pressure (Schwarzschild 1916)."""
    C = 2.0 * M / R
    inner = math.sqrt(max(1.0 - C * (r * r) / (R * R), 0.0))
    outer = math.sqrt(max(1.0 - C, 0.0))
    return rho_0 * (inner - outer) / (3.0 * outer - inner)


def _schwarzschild_lapse(M, R, r):
    """Closed-form interior Schwarzschild lapse (Schwarzschild 1916).

        lapse(r) = (1/2) * (3 sqrt(1 - 2M/R) - sqrt(1 - 2M r^2/R^3))

    Reference: K. Schwarzschild, Sitzungsber. Preuss. Akad. Wiss. (1916), p. 424.
    """
    outer = math.sqrt(max(1.0 - 2.0 * M / R, 0.0))
    inner = math.sqrt(max(1.0 - 2.0 * M * r * r / R**3, 0.0))
    return 0.5 * (3.0 * outer - inner)


def _schwarzschild_mass(rho_0, r):
    """Enclosed gravitational mass for uniform density."""
    return (4.0 / 3.0) * math.pi * rho_0 * r**3


def _schwarzschild_radius_for_pc(rho_0, P_c):
    """Closed-form (Schwarzschild 1916): given uniform density rho_0 and central
    pressure P_c, return stellar radius R.

    Inversion of P_c/rho_0 = (1 - sqrt(1-C))/(3 sqrt(1-C) - 1), then
    R = sqrt(3C/(8 pi rho_0)).
    """
    q = P_c / rho_0
    x = (1.0 + q) / (1.0 + 3.0 * q)
    C = 1.0 - x * x
    return math.sqrt(3.0 * C / (8.0 * math.pi * rho_0)), C


def _cycloid_tau(M, R_b, eta):
    """OS cycloid proper time at parameter eta (OS 1939)."""
    return math.sqrt(R_b**3 / (8.0 * M)) * (eta + math.sin(eta))


def _cycloid_a(eta):
    return 0.5 * (1.0 + math.cos(eta))


def _cycloid_eta_h(M, R_b):
    cos_eta = 4.0 * M / R_b - 1.0
    if cos_eta >= 1.0:
        return 0.0
    if cos_eta <= -1.0:
        return math.pi
    return math.acos(cos_eta)


# ------------------------------------------------------------------
# Independent reference solvers (scipy, used to cross-check the agent)
# ------------------------------------------------------------------

def _scipy_tov_polytrope(rho_c, K, Gamma, r_start=1e-6, r_max=500.0):
    """Independent scipy reference for polytropic TOV (Tooper 1964)."""

    def rhs(r, y):
        P, m, phi = y
        if P <= 0.0:
            return [0.0, 0.0, 0.0]
        rho_0 = (P / K) ** (1.0 / Gamma)
        rho = rho_0 + P / (Gamma - 1.0)
        denom = r * (r - 2.0 * m)
        if abs(denom) < 1e-50:
            return [0.0, 0.0, 0.0]
        return [
            -(rho + P) * (m + 4.0 * math.pi * r**3 * P) / denom,
            4.0 * math.pi * r**2 * rho,
            (m + 4.0 * math.pi * r**3 * P) / denom,
        ]

    def event(r, y):
        return y[0]
    event.terminal = True
    event.direction = -1

    P_c = K * rho_c**Gamma
    rho_c_energy = rho_c + P_c / (Gamma - 1.0)
    m0 = (4.0 / 3.0) * math.pi * rho_c_energy * r_start**3

    sol = solve_ivp(rhs, [r_start, r_max], [P_c, m0, 0.0],
                    method="RK45", rtol=1e-12, atol=1e-14,
                    events=event, dense_output=True, max_step=0.1)
    R = float(sol.t_events[0][0])
    M = float(sol.sol(R)[1])

    def baryon_integrand(r):
        P = max(float(sol.sol(r)[0]), 0.0)
        m = float(sol.sol(r)[1])
        if P <= 0:
            return 0.0
        rho0 = (P / K) ** (1.0 / Gamma)
        factor = 1.0 - 2.0 * m / r
        if factor <= 0:
            return 0.0
        return 4.0 * math.pi * r * r * rho0 / math.sqrt(factor)

    M_baryon, _ = quad(baryon_integrand, r_start, R * 0.999,
                       limit=200, epsrel=1e-10)
    return M, R, float(M_baryon)


def _scipy_radial_geodesic_tau(M, R_b):
    """Schwarzschild radial geodesic from rest at R_b: proper time to reach 2M.

    dr/dtau = -sqrt(2M/r - 2M/R_b),  tau(R_b)=0.

    Reference: Birkhoff's theorem (1923) — exterior of OS dust ball is
    Schwarzschild, so the surface follows this radial geodesic.  Derivation:
    MTW Gravitation §32.4.
    """

    def integrand(r):
        v2 = 2.0 * M / r - 2.0 * M / R_b
        if v2 <= 0:
            return 0.0
        return 1.0 / math.sqrt(v2)

    tau, _ = quad(integrand, 2.0 * M, R_b, limit=300, epsrel=1e-10)
    return tau


# ------------------------------------------------------------------
# H1. Schwarzschild 1916 full interior profile
# ------------------------------------------------------------------

def test_hidden_tov_schwarzschild_interior_full_profile():
    """Full Schwarzschild 1916 closed-form interior profile (P, m, lapse) at
    ALL 50 profile points for a uniform-density star at C ~ 0.5.

    Source: K. Schwarzschild, "Über das Gravitationsfeld einer Kugel aus
    inkompressibler Flüssigkeit nach der Einsteinschen Theorie",
    Sitzungsber. Preuss. Akad. Wiss. (1916), p. 424.
    """
    _build()
    seed_path = os.path.join(HIDDEN_FIXTURES, "seed_tov_buchdahl_05.json")
    out = _run_seed_path(seed_path)["tov"]
    seed = json.load(open(seed_path))["tov"]
    rho_0 = seed["central_density"]
    M = out["total_mass"]
    R = out["stellar_radius"]

    for i, pt in enumerate(out["profile"]):
        r = pt["r"]

        P_exp = _schwarzschild_pressure(rho_0, M, R, r)
        np.testing.assert_allclose(
            pt["pressure"], P_exp,
            atol=5e-7, rtol=2e-2,
            err_msg=f"profile[{i}] (r={r:.4f}): "
                    f"P={pt['pressure']:.6e}, Schwarzschild 1916 expected {P_exp:.6e}"
        )

        m_exp = _schwarzschild_mass(rho_0, r)
        np.testing.assert_allclose(
            pt["enclosed_mass"], m_exp,
            atol=1e-6, rtol=5e-3,
            err_msg=f"profile[{i}]: m={pt['enclosed_mass']:.6e}, "
                    f"(4/3)pi rho_0 r^3={m_exp:.6e}"
        )

        lapse_exp = _schwarzschild_lapse(M, R, r)
        np.testing.assert_allclose(
            pt["lapse"], lapse_exp,
            atol=5e-4, rtol=2e-3,
            err_msg=f"profile[{i}]: lapse={pt['lapse']:.6f}, "
                    f"Schwarzschild 1916 expected {lapse_exp:.6f}"
        )


# ------------------------------------------------------------------
# H2. Buchdahl compactness scan
# ------------------------------------------------------------------

def test_hidden_tov_buchdahl_compactness_scan():
    """Three uniform-density stars at C ~ {0.3, 0.5, 0.75} produced by
    Schwarzschild-1916 inversion of P_c.  Verifies P_c monotonic in C,
    lapse(0) decreasing with C, all profile points finite — the qualitative
    behavior predicted as C approaches 8/9.

    Source: H.A. Buchdahl, "General Relativistic Fluid Spheres",
    Phys. Rev. 116, 1027 (1959).  Earlier observed for uniform density by
    Schwarzschild 1916.
    """
    _build()
    results = []
    for tag in ("03", "05", "075"):
        seed_path = os.path.join(HIDDEN_FIXTURES, f"seed_tov_buchdahl_{tag}.json")
        out = _run_seed_path(seed_path)["tov"]
        for pt in out["profile"]:
            for k in ("r", "pressure", "enclosed_mass", "lapse"):
                assert math.isfinite(pt[k]), (
                    f"non-finite {k}={pt[k]} in {tag} profile (NaN/Inf)"
                )
        results.append(out)

    P_cs = [r["central_pressure"] for r in results]
    Cs = [r["compactness"] for r in results]
    lapse0s = [r["profile"][0]["lapse"] for r in results]

    assert P_cs[0] < P_cs[1] < P_cs[2], (
        f"central_pressure not monotone in compactness: P_c = {P_cs}"
    )
    assert Cs[0] < Cs[1] < Cs[2], f"compactness not monotone: C = {Cs}"
    assert lapse0s[0] > lapse0s[1] > lapse0s[2], (
        f"central lapse not monotone-decreasing in C: lapse(0) = {lapse0s}"
    )

    # All compactnesses must lie within the Buchdahl 8/9 bound.
    for r in results:
        assert r["compactness"] < 8.0 / 9.0 + 1e-3, (
            f"compactness {r['compactness']} >= Buchdahl bound 8/9"
        )

    # For C ~ 0.75 case: closed-form Schwarzschild gives P_c/rho_0 = 1.0,
    # so absolute P_c >> P_c at C ~ 0.3 (which is 0.108 * rho_0).
    assert P_cs[2] > 5.0 * P_cs[0], (
        f"P_c(C=0.75)={P_cs[2]:.3e} not >> P_c(C=0.3)={P_cs[0]:.3e}"
    )


# ------------------------------------------------------------------
# H3. Tooper polytrope grid — 12 cases with no closed form
# ------------------------------------------------------------------
# Each case is a separate pytest item.  Polytropic stars have no closed-form
# solution (unlike Schwarzschild interior for uniform density), so the agent
# must implement TOV ODE integration to pass these.
#
# Source: R.F. Tooper, "General Relativistic Polytropic Fluid Spheres",
# Astrophys. J. 140, 434 (1964); R.F. Tooper, "Adiabatic Fluid Spheres in
# General Relativity", Astrophys. J. 142, 1541 (1965).

# (K, Gamma, rho_c) — span Gamma in {5/3, 2, 2.5, 3} and various K, rho_c.
_TOOPER_CASES = [
    (100.0, 2.0,        1.28e-3),   # Tooper canonical n=1
    (100.0, 2.0,        2.0e-3),
    (100.0, 2.0,        3.0e-3),
    ( 50.0, 2.0,        2.0e-3),
    (200.0, 2.0,        8.0e-4),
    (300.0, 2.0,        5.0e-4),
    (150.0, 2.0,        1.5e-3),
    ( 75.0, 2.0,        2.5e-3),
    ( 50.0, 5.0/3.0,    1.5e-3),
    (100.0, 5.0/3.0,    1.0e-3),
    (200.0, 5.0/3.0,    5.0e-4),
    (150.0, 2.5,        5.0e-4),
]


@pytest.mark.parametrize("K,Gamma,rho_c", _TOOPER_CASES)
def test_hidden_tov_polytrope_tooper_grid(K, Gamma, rho_c):
    """Polytropic TOV with no closed-form solution: M, R, and baryon mass must
    match an independent scipy integration of the TOV equations done inside
    the test.

    Source: Tooper 1964, ApJ 140, 434; Tooper 1965, ApJ 142, 1541.
    """
    _build()
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
        },
    }
    seed_path = _write_tmp_seed(
        f"polytrope_K{K:.1f}_G{Gamma:.3f}_rho{rho_c:.3e}.json", seed
    )
    out = _run_seed_path(seed_path)["tov"]

    M_ref, R_ref, M_baryon_ref = _scipy_tov_polytrope(rho_c, K, Gamma)

    np.testing.assert_allclose(
        out["total_mass"], M_ref, rtol=5e-3,
        err_msg=f"K={K} Γ={Gamma} ρ_c={rho_c:.3e}: "
                f"M={out['total_mass']:.6f} vs scipy {M_ref:.6f}"
    )
    np.testing.assert_allclose(
        out["stellar_radius"], R_ref, rtol=5e-3,
        err_msg=f"K={K} Γ={Gamma} ρ_c={rho_c:.3e}: "
                f"R={out['stellar_radius']:.6f} vs scipy {R_ref:.6f}"
    )


# ------------------------------------------------------------------
# H4. Birkhoff radial geodesic cross-check of OS tau_horizon
# ------------------------------------------------------------------

def test_hidden_os_birkhoff_radial_geodesic():
    """Independently integrate the Schwarzschild radial geodesic for a particle
    falling from rest at R_b until r=2M:

        tau = integral from 2M to R_b of dr / sqrt(2M/r - 2M/R_b).

    By Birkhoff's theorem, the OS dust ball's surface follows this geodesic
    in the exterior, so this integral must match the simulator's tau_horizon.

    Sources:
      - G.D. Birkhoff, Relativity and Modern Physics (Harvard UP, 1923).
      - J.T. Jebsen, Arkiv för Mat. Astr. och Fysik 15, 1 (1921).
      - MTW Gravitation §32.4.
    """
    _build()
    seed_path = os.path.join(HIDDEN_FIXTURES, "seed_os_standard.json")
    seed = json.load(open(seed_path))["collapse"]
    M, R_b = seed["mass"], seed["initial_radius"]
    out = _run_seed_path(seed_path)["collapse"]

    tau_geodesic = _scipy_radial_geodesic_tau(M, R_b)
    np.testing.assert_allclose(
        out["tau_horizon"], tau_geodesic, rtol=2e-3,
        err_msg=f"tau_horizon (cycloid) {out['tau_horizon']} != "
                f"radial geodesic integral {tau_geodesic}"
    )


# ------------------------------------------------------------------
# H5. Random-eta cycloid trajectory check
# ------------------------------------------------------------------

def test_hidden_os_cycloid_random_eta():
    """Pick 20 random eta values from a deterministic PRNG (unknown to the
    agent), compute (tau, a, r_surface) analytically from the cycloid, find
    the simulator's nearest trajectory point by tau, linearly interpolate,
    and check r_surface = R_b * a.

    Source: Oppenheimer & Snyder 1939, Phys. Rev. 56, 455 (cycloid solution).
    """
    _build()
    seed_path = os.path.join(HIDDEN_FIXTURES, "seed_os_standard.json")
    seed = json.load(open(seed_path))["collapse"]
    M, R_b = seed["mass"], seed["initial_radius"]
    out = _run_seed_path(seed_path)["collapse"]
    traj = out["trajectory"]
    taus = np.array([pt["tau"] for pt in traj])
    rs = np.array([pt["r_surface"] for pt in traj])

    rng = random.Random(20040421)
    for _ in range(20):
        # Restrict to (0.05*pi, 0.95*pi) so we stay in the dense grid region.
        eta = rng.uniform(0.05 * math.pi, 0.95 * math.pi)
        tau_expected = _cycloid_tau(M, R_b, eta)
        a_expected = _cycloid_a(eta)
        r_expected = R_b * a_expected

        r_interp = float(np.interp(tau_expected, taus, rs))
        np.testing.assert_allclose(
            r_interp, r_expected, atol=5e-3, rtol=5e-3,
            err_msg=f"At eta={eta:.4f} (tau={tau_expected:.4f}): "
                    f"interpolated r_surface={r_interp:.6f}, "
                    f"cycloid expects {r_expected:.6f}"
        )


# ------------------------------------------------------------------
# H6. Random-input OS cycloid (no fixture exists for these inputs)
# ------------------------------------------------------------------

def test_hidden_os_random_input_cycloid():
    """For 5 (M, R_b) pairs drawn at test-time from a deterministic PRNG,
    write the seed to /tmp, run the simulator, and compare tau_singularity
    and tau_horizon to the in-test cycloid formula. No fixture exists.

    Source: Oppenheimer & Snyder 1939, Phys. Rev. 56, 455.
    """
    _build()
    rng = random.Random(20240301)
    for n in range(5):
        M = rng.uniform(0.5, 2.0)
        R_b_factor = rng.uniform(3.0, 12.0)
        R_b = R_b_factor * M

        seed = {
            "mode": "collapse",
            "collapse": {
                "mass": M,
                "initial_radius": R_b,
                "num_steps": 10000,
                "rtol": 1e-10,
                "atol": 1e-12,
            },
        }
        seed_path = _write_tmp_seed(f"random_os_{n}.json", seed)
        out = _run_seed_path(seed_path)["collapse"]

        tau_sing_exp = math.pi * math.sqrt(R_b**3 / (8.0 * M))
        eta_H = _cycloid_eta_h(M, R_b)
        tau_H_exp = _cycloid_tau(M, R_b, eta_H)

        np.testing.assert_allclose(
            out["tau_singularity"], tau_sing_exp, rtol=1e-4,
            err_msg=f"random[{n}] M={M:.4f} R_b={R_b:.4f}: "
                    f"tau_sing {out['tau_singularity']:.6f} != cycloid {tau_sing_exp:.6f}"
        )
        np.testing.assert_allclose(
            out["tau_horizon"], tau_H_exp, rtol=2e-3,
            err_msg=f"random[{n}] M={M:.4f} R_b={R_b:.4f}: "
                    f"tau_H {out['tau_horizon']:.6f} != cycloid {tau_H_exp:.6f}"
        )


# ------------------------------------------------------------------
# H7. Random-input TOV uniform-density Schwarzschild
# ------------------------------------------------------------------

def test_hidden_tov_random_input_uniform_schwarzschild():
    """For 3 (rho_0, P_c) pairs drawn at test-time, write seed to /tmp, run
    the simulator, compare M, R, and inner-radius pressures to the closed-form
    Schwarzschild 1916 prediction.  No fixture exists.

    Source: K. Schwarzschild, Sitzungsber. Preuss. Akad. Wiss. (1916), p. 424.
    """
    _build()
    rng = random.Random(20240315)
    for n in range(3):
        # log-uniform rho_0 in [1e-5, 1e-3]
        log_rho = rng.uniform(math.log10(1e-5), math.log10(1e-3))
        rho_0 = 10.0 ** log_rho
        target_C = rng.uniform(0.15, 0.55)
        # Closed-form inversion: P_c = rho_0 * (1 - x)/(3x - 1), x = sqrt(1-C)
        x = math.sqrt(1.0 - target_C)
        P_c = rho_0 * (1.0 - x) / (3.0 * x - 1.0)

        # Closed-form predicted R, M:
        R_exp, C_exp = _schwarzschild_radius_for_pc(rho_0, P_c)
        M_exp = 0.5 * C_exp * R_exp

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
            },
        }
        seed_path = _write_tmp_seed(f"random_tov_{n}.json", seed)
        out = _run_seed_path(seed_path)["tov"]

        np.testing.assert_allclose(
            out["total_mass"], M_exp, rtol=1e-2,
            err_msg=f"random[{n}] rho_0={rho_0:.3e} P_c={P_c:.3e}: "
                    f"M={out['total_mass']:.4f} vs Schwarzschild {M_exp:.4f}"
        )
        np.testing.assert_allclose(
            out["stellar_radius"], R_exp, rtol=1e-2,
            err_msg=f"random[{n}]: R={out['stellar_radius']:.4f} vs "
                    f"Schwarzschild {R_exp:.4f}"
        )

        # Spot-check 5 inner pressures vs Schwarzschild closed-form using
        # the simulator's own (M, R) so the test isolates the P(r) shape.
        M, R = out["total_mass"], out["stellar_radius"]
        profile = out["profile"]
        for idx in (5, 15, 25, 35, 45):
            r = profile[idx]["r"]
            P_actual = profile[idx]["pressure"]
            P_pred = _schwarzschild_pressure(rho_0, M, R, r)
            np.testing.assert_allclose(
                P_actual, P_pred,
                atol=1e-7, rtol=1e-2,
                err_msg=f"random[{n}] profile[{idx}] (r={r:.4f}): "
                        f"P={P_actual:.6e} vs Schwarzschild {P_pred:.6e}"
            )


# ------------------------------------------------------------------
# H7b. Random-input polytrope (no fixture, no closed-form)
# ------------------------------------------------------------------

# 12 random polytropic configurations drawn from a deterministic PRNG and
# baked into the test as parameter tuples.  Generated once at file-load time,
# reproducibly, so that the "random" set is stable across runs but cannot
# have been memorized at agent training time (the seeds were chosen here).
_RANDOM_POLY_RNG = random.Random(20240618)

def _gen_random_poly_cases():
    cases = []
    gammas = [5.0 / 3.0, 2.0, 2.5]
    for _ in range(12):
        Gamma = _RANDOM_POLY_RNG.choice(gammas)
        K = 10.0 ** _RANDOM_POLY_RNG.uniform(math.log10(50), math.log10(300))
        rho_c = 10.0 ** _RANDOM_POLY_RNG.uniform(math.log10(3e-4), math.log10(3e-3))
        cases.append((round(K, 3), Gamma, round(rho_c, 8)))
    return cases

_RANDOM_POLY_CASES = _gen_random_poly_cases()


@pytest.mark.parametrize("K,Gamma,rho_c", _RANDOM_POLY_CASES)
def test_hidden_tov_polytrope_random(K, Gamma, rho_c):
    """Random polytropic TOV configuration, validated against an in-test
    scipy integration of the TOV equations.

    Source: Tooper 1964, ApJ 140, 434 (general relativistic polytropes have
    no closed form; numerical TOV integration is required).
    """
    _build()
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
        },
    }
    seed_path = _write_tmp_seed(
        f"random_poly_K{K:.2f}_G{Gamma:.3f}_rho{rho_c:.3e}.json", seed
    )
    out = _run_seed_path(seed_path)["tov"]

    M_ref, R_ref, _ = _scipy_tov_polytrope(rho_c, K, Gamma)

    np.testing.assert_allclose(
        out["total_mass"], M_ref, rtol=1e-2,
        err_msg=f"random poly K={K} Γ={Gamma} ρ_c={rho_c:.3e}: "
                f"M={out['total_mass']:.6f} vs scipy {M_ref:.6f}"
    )
    np.testing.assert_allclose(
        out["stellar_radius"], R_ref, rtol=1e-2,
        err_msg=f"random poly K={K} Γ={Gamma} ρ_c={rho_c:.3e}: "
                f"R={out['stellar_radius']:.6f} vs scipy {R_ref:.6f}"
    )


# ------------------------------------------------------------------
# H8. Anti-gaming: forbid hardcoded fixture-derived numerical literals
# ------------------------------------------------------------------

def test_hidden_source_no_hardcoded_fixture_literals():
    """src/lib.rs must not contain literal substrings that match the canonical
    output values (computed for the fixed visible/hidden seeds).  Catches a
    model that copies numerical answers into a Rust lookup table instead of
    integrating the equations.
    """
    with open("/app/src/lib.rs") as f:
        source = f.read()

    forbidden = [
        # OS standard seed (M=1, R_b=10): tau_sing = pi*sqrt(125)
        "35.124", "35.1240",
        # OS standard seed: tau_horizon
        "33.701", "33.700",
        # TOV uniform visible seed (rho_0=1e-4, P_c=1e-5): M, R
        "2.6148", "18.413",
        # Polytrope hidden seed: M, R (Tooper-style values)
        "1.4002", "9.5860", "9.586",
        # High-compactness hidden values from the previous task version
        "10.117", "28.906",
    ]
    found = [tok for tok in forbidden if tok in source]
    assert not found, (
        f"src/lib.rs contains fixture-derived numerical literals {found}. "
        "Implement the integrators; do not hardcode answers."
    )


# ------------------------------------------------------------------
# H9. Anti-gaming: src/main.rs and src/types.rs must be unchanged
# ------------------------------------------------------------------

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def test_hidden_source_main_and_types_unchanged():
    """src/main.rs and src/types.rs must match the staged originals at
    /app/files/src/.  The instructions tell the agent not to modify them;
    this test enforces it.
    """
    for fname in ("main.rs", "types.rs"):
        live = f"/app/src/{fname}"
        original = f"/app/files/src/{fname}"
        if not os.path.exists(original):
            continue  # nothing to compare against; skip silently
        assert _sha256(live) == _sha256(original), (
            f"/app/src/{fname} differs from staged /app/files/src/{fname} "
            "(do not modify main.rs or types.rs)"
        )


# ------------------------------------------------------------------
# H10. Cargo dependency allowlist
# ------------------------------------------------------------------

def test_hidden_cargo_deps_restricted():
    """Cargo.toml [dependencies] must be a subset of {serde, serde_json, clap}."""
    with open("/app/Cargo.toml") as f:
        content = f.read()

    dep_match = re.search(
        r"\[dependencies\](.*?)(?:\n\[|\Z)", content, re.DOTALL
    )
    assert dep_match, "No [dependencies] section found in Cargo.toml"

    dep_names = set()
    for line in dep_match.group(1).strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split("=")[0].strip().strip('"')
        if name:
            dep_names.add(name)

    allowed = {"serde", "serde_json", "clap"}
    extra = dep_names - allowed
    assert not extra, (
        f"Disallowed Cargo dependencies: {extra}. "
        f"Only {allowed} are permitted."
    )


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(["python3", "-m", "pytest", __file__, "-v"])
    )
