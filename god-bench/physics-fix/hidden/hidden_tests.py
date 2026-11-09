import math
import random
import shutil
import subprocess
from pathlib import Path

FILES = Path("/app/files")
APP = Path("/app")

HIDDEN_RUST = r'''
use event_ode::{collapse_event, localize_event, pressure_zero, DenseStep, Direction};

fn close(a: f64, b: f64, tol: f64) { assert!((a-b).abs() <= tol, "{a:e} != {b:e}"); }

#[test]
fn generated_pressure_and_time_reparameterization() {
    let mut x = 0x9e3779b97f4a7c15_u64;
    for _ in 0..80 {
        x ^= x << 7; x ^= x >> 9; x ^= x << 8;
        let p = 10f64.powf(-6.0 + 9.0 * (x as f64 / u64::MAX as f64));
        let hit = pressure_zero(p).unwrap();
        close(hit.t, p.sqrt(), 3e-8 * p.sqrt().max(1.0));

        let scale = 0.1 + 7.0 * ((x.rotate_left(17) as f64) / u64::MAX as f64);
        let step = DenseStep::from_endpoints(
            0.0, 2.0 * scale, vec![-1.0], vec![7.0], vec![0.0], vec![12.0 / scale]);
        let root = localize_event(&step, &|_, y| y[0], Direction::Rising, 1e-12, 1e-12).unwrap();
        close(root.t / scale, 1.0, 2e-10);
        close(root.state[0], 0.0, 2e-10);
    }
}

#[test]
fn generated_collapse_matches_independent_integral_and_scaling() {
    for i in 1..35 {
        let m = 0.05 + i as f64 * 0.071;
        let r0 = (2.5 + (i % 9) as f64) * m;
        let cutoff = (0.08 + (i % 5) as f64 * 0.11) * m;
        let hit = collapse_event(m, r0, cutoff).unwrap();
        let expected = (2.0 / 3.0) * (r0.powf(1.5) - cutoff.powf(1.5)) / (2.0 * m).sqrt();
        close(hit.t, expected, 5e-6 * expected.max(1.0));
        close(hit.state[0], cutoff, 3e-9 * r0.max(1.0));
        let scaled = collapse_event(11.0*m, 11.0*r0, 11.0*cutoff).unwrap();
        close(scaled.t / hit.t, 11.0, 3e-5);
    }
}

#[test]
fn adversarial_flat_root_bad_scale_and_non_brackets() {
    for power in [3_i32, 5, 7] {
        let step = DenseStep::from_endpoints(-0.9, 1.4, vec![-0.9], vec![1.4], vec![1.0], vec![1.0]);
        for scale in [1e-180_f64, 1.0, 1e180] {
            let hit = localize_event(&step, &|_, y| scale * (y[0] - 0.123456789).powi(power), Direction::Rising, 1e-12, scale * 1e-30).unwrap();
            close(hit.t, 0.123456789, 3e-10);
        }
    }
    let step = DenseStep::from_endpoints(0.0, 1.0, vec![2.0], vec![3.0], vec![1.0], vec![1.0]);
    assert!(localize_event(&step, &|_, y| y[0], Direction::Any, 1e-12, 1e-12).is_none());
}

#[test]
fn single_input_mutation_changes_only_the_expected_surface() {
    let p = 0.417_f64;
    let base = pressure_zero(p).unwrap();
    let changed = pressure_zero(p * (1.0 + 1e-6)).unwrap();
    assert!(changed.t > base.t);
    close(changed.t / base.t, (1.0 + 1e-6_f64).sqrt(), 2e-9);
}
'''


def _stage():
    shutil.rmtree(APP / "src", ignore_errors=True)
    shutil.rmtree(APP / "tests", ignore_errors=True)
    shutil.copytree(FILES / "src", APP / "src")
    (APP / "tests").mkdir()
    (APP / "tests" / "hidden_generated.rs").write_text(HIDDEN_RUST)
    shutil.copyfile(FILES / "Cargo.toml", APP / "Cargo.toml")


def test_generated_and_metamorphic_events():
    _stage()
    result = subprocess.run(
        ["cargo", "test", "--release", "--offline", "--test", "hidden_generated"],
        cwd=APP, capture_output=True, text=True, timeout=240,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]


def test_candidate_artifact_is_only_kernel_and_reachable():
    source = (FILES / "src" / "event.rs").read_text()
    scaffold = (FILES / "src" / "lib.rs").read_text()
    assert "pub fn localize_event" in source
    assert "localize_event(&step" in scaffold
    assert len(source.encode()) < 14000
    assert not any(path.is_symlink() for path in (FILES / "src").iterdir())
    assert {p.name for p in (FILES / "src").iterdir()} == {"lib.rs", "event.rs"}
