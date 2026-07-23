use gr_sim::{polytropic_eos, rk45_step};


#[test]
fn randomized_eos_is_deterministic_and_physical() {
    let mut state = 0xbb67_ae85_84ca_a73b_u64;
    for _ in 0..97 {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        let unit = (state as f64) / (u64::MAX as f64);
        let rho0 = 10_f64.powf(-7.0 + 6.0 * unit);

        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        let unit = (state as f64) / (u64::MAX as f64);
        let k = 10_f64.powf(-2.0 + 5.0 * unit);

        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        let unit = (state as f64) / (u64::MAX as f64);
        let gamma = 1.1 + 2.4 * unit;

        let expected_p = k * rho0.powf(gamma);
        let expected_rho = rho0 + expected_p / (gamma - 1.0);
        let first = polytropic_eos(rho0, k, gamma);
        let second = polytropic_eos(rho0, k, gamma);
        assert_eq!(first, second, "EOS must be deterministic");
        assert!(first.0 >= 0.0 && first.1 >= rho0);
        assert!((first.0 - expected_p).abs() <= 2e-13 * expected_p.max(1e-300));
        assert!((first.1 - expected_rho).abs() <= 2e-13 * expected_rho);
    }
}


#[test]
fn rk45_fifth_order_solution_improves_with_half_steps() {
    let rhs = |t: f64, y: &[f64]| vec![y[1], -y[0] + t.sin()];
    let y0 = [0.25, -0.5];
    let reference_step = |steps: usize| {
        let h = 0.3 / steps as f64;
        let mut t = 0.0;
        let mut y = y0.to_vec();
        let mut max_error_estimate: f64 = 0.0;
        for _ in 0..steps {
            let (next, estimate) = rk45_step(&rhs, t, &y, h);
            assert!(next.iter().all(|value| value.is_finite()));
            assert!(estimate.is_finite() && estimate >= 0.0);
            max_error_estimate = max_error_estimate.max(estimate);
            y = next;
            t += h;
        }
        (y, max_error_estimate)
    };

    let (coarse, coarse_estimate) = reference_step(1);
    let (fine, fine_estimate) = reference_step(2);
    let (reference, _) = reference_step(64);
    let norm = |a: &[f64], b: &[f64]| {
        a.iter()
            .zip(b)
            .map(|(x, y)| (*x - *y).abs())
            .fold(0.0, f64::max)
    };
    let coarse_error = norm(&coarse, &reference);
    let fine_error = norm(&fine, &reference);
    assert!(
        fine_error < coarse_error / 8.0,
        "step halving did not improve RK45 convergence"
    );
    assert!(
        fine_estimate < coarse_estimate,
        "embedded estimate did not decrease"
    );
}
