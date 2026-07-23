use gr_sim::{polytropic_eos, rk45_step};


#[test]
fn polytropic_eos_matches_formula_for_deterministic_cases() {
    let mut state = 0x6a09_e667_f3bc_c909_u64;
    for _ in 0..64 {
        state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
        let u1 = ((state >> 11) as f64) * (1.0 / ((1_u64 << 53) as f64));
        state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
        let u2 = ((state >> 11) as f64) * (1.0 / ((1_u64 << 53) as f64));
        state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
        let u3 = ((state >> 11) as f64) * (1.0 / ((1_u64 << 53) as f64));

        let rho0 = 10_f64.powf(-6.0 + 5.0 * u1);
        let k = 10_f64.powf(-1.0 + 3.5 * u2);
        let gamma = 1.2 + 1.8 * u3;
        let expected_p = k * rho0.powf(gamma);
        let expected_rho = rho0 + expected_p / (gamma - 1.0);
        let (p, rho) = polytropic_eos(rho0, k, gamma);

        assert!(p.is_finite() && rho.is_finite());
        assert!((p - expected_p).abs() <= 2e-13 * expected_p.max(1e-300));
        assert!((rho - expected_rho).abs() <= 2e-13 * expected_rho);
    }
}


#[test]
fn rk45_reports_finite_error_and_converges_under_step_halving() {
    let rhs = |_t: f64, y: &[f64]| vec![y[0], -2.0 * y[1]];
    let y0 = [1.0, 1.0];
    let h = 0.2;

    let (full, err_full) = rk45_step(&rhs, 0.0, &y0, h);
    let (half, err_half_1) = rk45_step(&rhs, 0.0, &y0, h / 2.0);
    let (two_half, err_half_2) = rk45_step(&rhs, h / 2.0, &half, h / 2.0);

    assert_eq!(full.len(), y0.len());
    assert_eq!(half.len(), y0.len());
    assert_eq!(two_half.len(), y0.len());
    assert!(err_full.is_finite() && err_full > 0.0);
    assert!(err_half_1.is_finite() && err_half_1 >= 0.0);
    assert!(err_half_2.is_finite() && err_half_2 >= 0.0);

    let exact = [h.exp(), (-2.0 * h).exp()];
    let full_error = full
        .iter()
        .zip(exact)
        .map(|(a, b)| (*a - b).abs())
        .fold(0.0, f64::max);
    let half_error = two_half
        .iter()
        .zip(exact)
        .map(|(a, b)| (*a - b).abs())
        .fold(0.0, f64::max);
    assert!(full_error < 1e-6, "full-step error was {full_error:e}");
    assert!(
        half_error < full_error / 8.0,
        "step halving did not converge: {full_error:e} -> {half_error:e}"
    );
    assert!(
        err_half_1.max(err_half_2) < err_full,
        "embedded error did not decrease under step halving"
    );
}
