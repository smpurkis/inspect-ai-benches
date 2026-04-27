import json
import os
import subprocess

import numpy as np

BINARY = "/app/target/release/gr_sim"
FIXTURES = "/app/files/fixtures"


def _build():
    result = subprocess.run(
        ["cargo", "build", "--release"],
        capture_output=True,
        text=True,
        cwd="/app",
        timeout=300,
    )
    return result


def _run_sim(seed_file):
    result = subprocess.run(
        [BINARY, "--input", seed_file],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result


# ------------------------------------------------------------------
# 1. Build test
# ------------------------------------------------------------------

def test_builds():
    """cargo build --release succeeds."""
    result = _build()
    assert result.returncode == 0, f"cargo build failed:\n{result.stderr[-3000:]}"


# ------------------------------------------------------------------
# 2. TOV uniform density
# ------------------------------------------------------------------

def test_tov_uniform_density():
    """TOV with uniform density: M, R, and mid-radius pressure match reference."""
    result = _build()
    assert result.returncode == 0, f"Build failed:\n{result.stderr[-2000:]}"

    seed = os.path.join(FIXTURES, "seed_tov_uniform.json")
    ref_file = os.path.join(FIXTURES, "reference_tov_uniform.json")

    r = _run_sim(seed)
    assert r.returncode == 0, (
        f"Simulator crashed:\nstdout={r.stdout[:500]}\nstderr={r.stderr[:500]}"
    )

    output = json.loads(r.stdout)
    with open(ref_file) as f:
        reference = json.load(f)

    out_tov = output["tov"]
    ref_tov = reference["tov"]

    # Total mass
    np.testing.assert_allclose(
        out_tov["total_mass"], ref_tov["total_mass"],
        atol=1e-5,
        err_msg="Total mass mismatch",
    )

    # Stellar radius
    np.testing.assert_allclose(
        out_tov["stellar_radius"], ref_tov["stellar_radius"],
        atol=1e-5,
        err_msg="Stellar radius mismatch",
    )

    # Mid-radius pressure (profile point near R/2)
    out_profile = out_tov["profile"]
    ref_profile = ref_tov["profile"]
    mid_idx = len(ref_profile) // 2
    np.testing.assert_allclose(
        out_profile[mid_idx]["pressure"],
        ref_profile[mid_idx]["pressure"],
        atol=1e-5,
        err_msg=f"Pressure mismatch at profile index {mid_idx}",
    )


# ------------------------------------------------------------------
# 3. OS collapse singularity time
# ------------------------------------------------------------------

def test_os_collapse_time():
    """OS collapse: tau_singularity matches analytical value within rtol=1e-4."""
    result = _build()
    assert result.returncode == 0, f"Build failed:\n{result.stderr[-2000:]}"

    seed = os.path.join(FIXTURES, "seed_os_standard.json")
    ref_file = os.path.join(FIXTURES, "reference_os_standard.json")

    r = _run_sim(seed)
    assert r.returncode == 0, (
        f"Simulator crashed:\nstdout={r.stdout[:500]}\nstderr={r.stderr[:500]}"
    )

    output = json.loads(r.stdout)
    with open(ref_file) as f:
        reference = json.load(f)

    np.testing.assert_allclose(
        output["collapse"]["tau_singularity"],
        reference["collapse"]["tau_singularity"],
        rtol=1e-4,
        err_msg="tau_singularity mismatch",
    )


# ------------------------------------------------------------------
# 4. OS horizon crossing
# ------------------------------------------------------------------

def test_os_horizon_crossing():
    """OS collapse: tau_H within rtol=1e-3, r(tau_H)=2M within atol=1e-5."""
    result = _build()
    assert result.returncode == 0, f"Build failed:\n{result.stderr[-2000:]}"

    seed = os.path.join(FIXTURES, "seed_os_standard.json")
    ref_file = os.path.join(FIXTURES, "reference_os_standard.json")

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
        out_col["tau_horizon"],
        ref_col["tau_horizon"],
        rtol=1e-3,
        err_msg="tau_horizon mismatch",
    )

    np.testing.assert_allclose(
        out_col["horizon_radius"],
        ref_col["horizon_radius"],
        atol=1e-5,
        err_msg="horizon_radius mismatch",
    )


# ------------------------------------------------------------------
# 5. Energy conservation
# ------------------------------------------------------------------

def test_energy_conservation():
    """Friedmann energy drift must be < 1e-8 over the collapse trajectory."""
    result = _build()
    assert result.returncode == 0, f"Build failed:\n{result.stderr[-2000:]}"

    seed = os.path.join(FIXTURES, "seed_os_standard.json")

    r = _run_sim(seed)
    assert r.returncode == 0, f"Simulator failed:\n{r.stderr[:500]}"

    output = json.loads(r.stdout)
    drift = output["collapse"]["energy_drift_max"]
    assert drift < 1e-8, (
        f"Energy drift {drift:.2e} exceeds tolerance 1e-8"
    )


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(["python3", "-m", "pytest", __file__, "-v"])
    )
