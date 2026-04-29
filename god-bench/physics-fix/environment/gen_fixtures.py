#!/usr/bin/env python3
"""
Generate seed fixture files for the GR collapse benchmark.

Hardened version: emits ONLY seed JSONs.  Reference values are no longer
shipped — visible and hidden tests compute expected values inside the test
from closed-form GR formulas (Schwarzschild 1916 interior, Oppenheimer-Snyder
1939 cycloid) or via independent numerical integration at verify time.

Seeds emitted:
  Visible (/files/fixtures/):
    seed_tov_uniform.json     — uniform density, moderate compactness
    seed_os_standard.json     — OS dust ball M=1, R_b=10

  Hidden (/hidden/fixtures/):
    seed_tov_polytrope.json           — K=100, Gamma=2, rho_c=1.28e-3
    seed_tov_buchdahl_03.json         — uniform, target C ~ 0.3
    seed_tov_buchdahl_05.json         — uniform, target C ~ 0.5
    seed_tov_buchdahl_075.json        — uniform, target C ~ 0.75
    seed_os_standard.json             — same as visible (used by H4, H5)

All quantities in geometric units: G = c = 1.
"""

import json
import math
import os


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


def schwarzschild_pc_for_compactness(rho_0, target_C):
    """Closed-form (Schwarzschild 1916) inversion: given uniform density rho_0
    and target compactness C = 2M/R, return the central pressure P_c.

    Derivation: for uniform-density Schwarzschild interior,
        P_c / rho_0 = (1 - sqrt(1-C)) / (3*sqrt(1-C) - 1).
    Reference: K. Schwarzschild, Sitzungsber. Preuss. Akad. Wiss. (1916) p.424.
    """
    if not (0 < target_C < 8.0 / 9.0):
        raise ValueError(f"compactness {target_C} outside (0, 8/9)")
    x = math.sqrt(1.0 - target_C)
    return rho_0 * (1.0 - x) / (3.0 * x - 1.0)


def gen_visible_tov_uniform():
    """Visible seed: uniform density rho_0=1e-4, P_c=1e-5 (C ~ 0.284)."""
    print("Visible: TOV uniform density seed...")
    seed = {
        "mode": "tov",
        "tov": {
            "central_density": 1e-4,
            "central_pressure": 1e-5,
            "eos_k": 0.0,
            "eos_gamma": 0.0,
            "uniform_density": True,
            "r_start": 1e-6,
            "dr_initial": 0.01,
            "rtol": 1e-10,
            "atol": 1e-12,
        },
    }
    write_json(os.path.join(FILES_FIXTURES, "seed_tov_uniform.json"), seed)


def gen_visible_os_standard():
    """Visible seed: OS dust ball M=1, R_b=10."""
    print("Visible: OS standard seed...")
    seed = {
        "mode": "collapse",
        "collapse": {
            "mass": 1.0,
            "initial_radius": 10.0,
            "num_steps": 10000,
            "rtol": 1e-10,
            "atol": 1e-12,
        },
    }
    write_json(os.path.join(FILES_FIXTURES, "seed_os_standard.json"), seed)


def gen_hidden_tov_polytrope():
    """Hidden seed: K=100, Gamma=2, rho_c=1.28e-3 (Tooper 1964 n=1)."""
    print("Hidden: TOV polytrope (Tooper Gamma=2) seed...")
    seed = {
        "mode": "tov",
        "tov": {
            "central_density": 1.28e-3,
            "eos_k": 100.0,
            "eos_gamma": 2.0,
            "uniform_density": False,
            "r_start": 1e-6,
            "dr_initial": 0.01,
            "rtol": 1e-10,
            "atol": 1e-12,
        },
    }
    write_json(os.path.join(HIDDEN_FIXTURES, "seed_tov_polytrope.json"), seed)


def gen_hidden_tov_buchdahl_scan():
    """Hidden seeds: 3 uniform-density stars at C ~ 0.3, 0.5, 0.75
    (Buchdahl 1959 limit is 8/9). P_c computed from Schwarzschild 1916 inverse.
    """
    print("Hidden: TOV Buchdahl compactness-scan seeds...")
    rho_0 = 1e-4
    for tag, target_C in [("03", 0.30), ("05", 0.50), ("075", 0.75)]:
        P_c = schwarzschild_pc_for_compactness(rho_0, target_C)
        seed = {
            "mode": "tov",
            "tov": {
                "central_density": rho_0,
                "central_pressure": P_c,
                "eos_k": 0.0,
                "eos_gamma": 0.0,
                "uniform_density": True,
                "r_start": 1e-6,
                "dr_initial": 0.001 if target_C >= 0.5 else 0.01,
                "rtol": 1e-10,
                "atol": 1e-12,
            },
        }
        write_json(
            os.path.join(HIDDEN_FIXTURES, f"seed_tov_buchdahl_{tag}.json"),
            seed,
        )
        print(f"    target C={target_C}: P_c={P_c:.6e}")


def gen_hidden_os_standard():
    """Hidden seed: same as visible OS standard (used by H4 Birkhoff and H5
    random-eta cycloid checks). Duplicating in /hidden/fixtures keeps the
    test's I/O paths self-contained."""
    print("Hidden: OS standard seed (mirror of visible)...")
    seed = {
        "mode": "collapse",
        "collapse": {
            "mass": 1.0,
            "initial_radius": 10.0,
            "num_steps": 10000,
            "rtol": 1e-10,
            "atol": 1e-12,
        },
    }
    write_json(os.path.join(HIDDEN_FIXTURES, "seed_os_standard.json"), seed)


def main():
    print("=" * 60)
    print("Generating GR collapse benchmark seed fixtures")
    print("(reference values are computed in-test, not shipped)")
    print("=" * 60)

    gen_visible_tov_uniform()
    gen_visible_os_standard()

    gen_hidden_tov_polytrope()
    gen_hidden_tov_buchdahl_scan()
    gen_hidden_os_standard()

    print("=" * 60)
    print("All seed fixtures generated successfully.")


if __name__ == "__main__":
    main()
