import json
import math
import os
import subprocess

import numpy as np

BINARY = "/app/target/release/gr_sim"
HIDDEN_FIXTURES = "/app/hidden/fixtures"


def _build():
    result = subprocess.run(
        ["cargo", "build", "--release"],
        capture_output=True,
        text=True,
        cwd="/app",
        timeout=300,
    )
    assert result.returncode == 0, f"Build failed:\n{result.stderr[-2000:]}"


def _run_sim(seed_file):
    result = subprocess.run(
        [BINARY, "--input", seed_file],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result


# ------------------------------------------------------------------
# 1. TOV polytrope: K=100, Gamma=2, rho_c=1.28e-3
# ------------------------------------------------------------------

def test_hidden_tov_polytrope():
    """TOV polytrope: M and R within rtol=1e-3."""
    _build()

    seed = os.path.join(HIDDEN_FIXTURES, "seed_tov_polytrope.json")
    ref_file = os.path.join(HIDDEN_FIXTURES, "reference_tov_polytrope.json")

    r = _run_sim(seed)
    assert r.returncode == 0, (
        f"Simulator crashed:\nstdout={r.stdout[:500]}\nstderr={r.stderr[:500]}"
    )

    output = json.loads(r.stdout)
    with open(ref_file) as f:
        reference = json.load(f)

    out_tov = output["tov"]
    ref_tov = reference["tov"]

    np.testing.assert_allclose(
        out_tov["total_mass"], ref_tov["total_mass"],
        rtol=1e-3,
        err_msg="Polytrope total mass mismatch",
    )
    np.testing.assert_allclose(
        out_tov["stellar_radius"], ref_tov["stellar_radius"],
        rtol=1e-3,
        err_msg="Polytrope stellar radius mismatch",
    )


# ------------------------------------------------------------------
# 2. TOV surface pressure must be zero
# ------------------------------------------------------------------

def test_hidden_tov_surface_pressure_zero():
    """The last profile point must have P < 1e-10."""
    _build()

    seed = os.path.join(HIDDEN_FIXTURES, "seed_tov_polytrope.json")
    r = _run_sim(seed)
    assert r.returncode == 0, f"Simulator crashed:\n{r.stderr[:500]}"

    output = json.loads(r.stdout)
    profile = output["tov"]["profile"]

    # Last profile point (at 0.999 * R) should have very small pressure.
    last_p = profile[-1]["pressure"]
    assert last_p < 1e-10, (
        f"Surface pressure too large: {last_p:.2e} (should be < 1e-10)"
    )


# ------------------------------------------------------------------
# 3. TOV Buchdahl limit: high compactness, P_c finite, no NaN
# ------------------------------------------------------------------

def test_hidden_tov_buchdahl_limit():
    """High compactness (2M/R ~ 0.7): P_c is large but finite, no NaN."""
    _build()

    seed = os.path.join(HIDDEN_FIXTURES, "seed_tov_high_compactness.json")
    ref_file = os.path.join(HIDDEN_FIXTURES, "reference_tov_high_compactness.json")

    r = _run_sim(seed)
    assert r.returncode == 0, (
        f"Simulator crashed:\nstdout={r.stdout[:500]}\nstderr={r.stderr[:500]}"
    )

    output = json.loads(r.stdout)
    with open(ref_file) as f:
        reference = json.load(f)

    out_tov = output["tov"]
    ref_tov = reference["tov"]

    # Central pressure must be finite and positive
    assert math.isfinite(out_tov["central_pressure"]), "P_c is not finite"
    assert out_tov["central_pressure"] > 0, "P_c is not positive"

    # No NaN in profile
    for pt in out_tov["profile"]:
        for key in ("r", "pressure", "enclosed_mass", "lapse"):
            assert math.isfinite(pt[key]), (
                f"NaN/Inf in profile at r={pt['r']}: {key}={pt[key]}"
            )

    # Compactness should be close to 0.7
    np.testing.assert_allclose(
        out_tov["compactness"], ref_tov["compactness"],
        rtol=1e-2,
        err_msg="High-compactness compactness mismatch",
    )


# ------------------------------------------------------------------
# 4. TOV lapse at surface matches exterior Schwarzschild
# ------------------------------------------------------------------

def test_hidden_tov_lapse_at_surface():
    """phi(R) = 0.5 * ln(1 - 2M/R) within atol=1e-5."""
    _build()

    seed = os.path.join(HIDDEN_FIXTURES, "seed_tov_uniform.json")
    ref_file = os.path.join(HIDDEN_FIXTURES, "reference_tov_uniform.json")

    r = _run_sim(seed)
    assert r.returncode == 0, f"Simulator crashed:\n{r.stderr[:500]}"

    output = json.loads(r.stdout)
    with open(ref_file) as f:
        reference = json.load(f)

    out_tov = output["tov"]
    ref_tov = reference["tov"]

    # The lapse at the last profile point (near surface) should match reference
    out_lapse = out_tov["profile"][-1]["lapse"]
    ref_lapse = ref_tov["profile"][-1]["lapse"]

    np.testing.assert_allclose(
        out_lapse, ref_lapse,
        atol=1e-5,
        err_msg="Lapse at surface mismatch",
    )


# ------------------------------------------------------------------
# 5. OS trajectory checkpoints match analytical cycloid
# ------------------------------------------------------------------

def test_hidden_os_trajectory_checkpoints():
    """r(tau) at 20 equally-spaced tau values match analytical within atol=1e-5."""
    _build()

    seed = os.path.join(HIDDEN_FIXTURES, "seed_os_standard.json")
    ref_file = os.path.join(HIDDEN_FIXTURES, "reference_os_standard.json")

    r = _run_sim(seed)
    assert r.returncode == 0, f"Simulator crashed:\n{r.stderr[:500]}"

    output = json.loads(r.stdout)
    with open(ref_file) as f:
        reference = json.load(f)

    out_traj = output["collapse"]["trajectory"]
    ref_traj = reference["collapse"]["trajectory"]

    # Check at 20 evenly-spaced indices
    n = len(ref_traj)
    assert len(out_traj) >= n, (
        f"Trajectory too short: {len(out_traj)} < {n}"
    )

    step = max(1, n // 20)
    for i in range(0, n, step):
        np.testing.assert_allclose(
            out_traj[i]["r_surface"],
            ref_traj[i]["r_surface"],
            atol=1e-5,
            err_msg=f"r_surface mismatch at trajectory index {i}",
        )
        np.testing.assert_allclose(
            out_traj[i]["tau"],
            ref_traj[i]["tau"],
            atol=1e-5,
            err_msg=f"tau mismatch at trajectory index {i}",
        )


# ------------------------------------------------------------------
# 6. OS different config: M=0.5, R_b=5.0
# ------------------------------------------------------------------

def test_hidden_os_different_config():
    """OS compact: M=0.5, R_b=5.0 -- tau_sing and tau_H correct."""
    _build()

    seed = os.path.join(HIDDEN_FIXTURES, "seed_os_compact.json")
    ref_file = os.path.join(HIDDEN_FIXTURES, "reference_os_compact.json")

    r = _run_sim(seed)
    assert r.returncode == 0, (
        f"Simulator crashed:\nstdout={r.stdout[:500]}\nstderr={r.stderr[:500]}"
    )

    output = json.loads(r.stdout)
    with open(ref_file) as f:
        reference = json.load(f)

    out_col = output["collapse"]
    ref_col = reference["collapse"]

    np.testing.assert_allclose(
        out_col["tau_singularity"], ref_col["tau_singularity"],
        rtol=1e-4,
        err_msg="Compact tau_singularity mismatch",
    )
    np.testing.assert_allclose(
        out_col["tau_horizon"], ref_col["tau_horizon"],
        rtol=1e-3,
        err_msg="Compact tau_horizon mismatch",
    )


# ------------------------------------------------------------------
# 7. OS near horizon: no NaN/Inf
# ------------------------------------------------------------------

def test_hidden_os_near_horizon_no_nan():
    """Trajectory near r=2M must contain no NaN or Inf."""
    _build()

    seed = os.path.join(HIDDEN_FIXTURES, "seed_os_standard.json")
    r = _run_sim(seed)
    assert r.returncode == 0, f"Simulator crashed:\n{r.stderr[:500]}"

    output = json.loads(r.stdout)
    traj = output["collapse"]["trajectory"]

    for pt in traj:
        for key in ("tau", "r_surface", "scale_factor", "energy"):
            val = pt[key]
            assert math.isfinite(val), (
                f"NaN/Inf in trajectory at tau={pt['tau']}: {key}={val}"
            )


# ------------------------------------------------------------------
# 8. TOV baryon mass
# ------------------------------------------------------------------

def test_hidden_tov_baryon_mass():
    """Baryon mass matches reference within rtol=1e-3."""
    _build()

    seed = os.path.join(HIDDEN_FIXTURES, "seed_tov_polytrope.json")
    ref_file = os.path.join(HIDDEN_FIXTURES, "reference_tov_polytrope.json")

    r = _run_sim(seed)
    assert r.returncode == 0, f"Simulator crashed:\n{r.stderr[:500]}"

    output = json.loads(r.stdout)
    with open(ref_file) as f:
        reference = json.load(f)

    np.testing.assert_allclose(
        output["tov"]["baryon_mass"],
        reference["tov"]["baryon_mass"],
        rtol=1e-3,
        err_msg="Baryon mass mismatch",
    )


# ------------------------------------------------------------------
# 9. OS marginal: R_b = 2.5 M (near horizon start)
# ------------------------------------------------------------------

def test_hidden_os_marginal():
    """Collapse starting near the horizon (R_b = 2.5 M) still completes."""
    _build()

    seed = os.path.join(HIDDEN_FIXTURES, "seed_os_marginal.json")
    ref_file = os.path.join(HIDDEN_FIXTURES, "reference_os_marginal.json")

    r = _run_sim(seed)
    assert r.returncode == 0, (
        f"Simulator crashed:\nstdout={r.stdout[:500]}\nstderr={r.stderr[:500]}"
    )

    output = json.loads(r.stdout)
    with open(ref_file) as f:
        reference = json.load(f)

    out_col = output["collapse"]
    ref_col = reference["collapse"]

    np.testing.assert_allclose(
        out_col["tau_singularity"], ref_col["tau_singularity"],
        rtol=1e-3,
        err_msg="Marginal tau_singularity mismatch",
    )
    np.testing.assert_allclose(
        out_col["tau_horizon"], ref_col["tau_horizon"],
        rtol=1e-2,
        err_msg="Marginal tau_horizon mismatch",
    )


# ------------------------------------------------------------------
# 10. Cargo deps restricted
# ------------------------------------------------------------------

def test_hidden_cargo_deps_restricted():
    """Cargo.toml only lists serde, serde_json, and clap as dependencies."""
    import re

    with open("/app/Cargo.toml") as f:
        content = f.read()

    # Find [dependencies] section
    dep_match = re.search(
        r"\[dependencies\](.*?)(?:\n\[|\Z)", content, re.DOTALL
    )
    assert dep_match, "No [dependencies] section found in Cargo.toml"

    deps_text = dep_match.group(1)

    # Extract dependency names (handle both inline table and simple forms)
    dep_names = set()
    for line in deps_text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split("=")[0].strip().strip('"')
        if name:
            dep_names.add(name)

    allowed = {"serde", "serde_json", "clap"}
    extra = dep_names - allowed
    assert not extra, (
        f"Disallowed dependencies found: {extra}. "
        f"Only {allowed} are permitted."
    )


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(["python3", "-m", "pytest", __file__, "-v"])
    )
