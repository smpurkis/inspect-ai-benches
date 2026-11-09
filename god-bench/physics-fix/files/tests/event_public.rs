use event_ode::{collapse_event, horizon_event, localize_event, pressure_zero, DenseStep, Direction};

#[test]
fn normal_pressure_zero_uses_dense_state() {
    let hit = pressure_zero(2.0).expect("pressure surface");
    assert!((hit.t - 2.0_f64.sqrt()).abs() < 2e-8, "t={}", hit.t);
    assert!(hit.value.abs() < 1e-10);
    assert!(hit.state[0].abs() < 1e-10);
}

#[test]
fn edge_endpoint_and_direction_are_respected() {
    let step = DenseStep::from_endpoints(2.0, 3.0, vec![0.0], vec![1.0], vec![1.0], vec![1.0]);
    let rising = localize_event(&step, &|_, y| y[0], Direction::Rising, 1e-12, 1e-12).unwrap();
    assert_eq!(rising.t, 2.0);
    assert!(localize_event(&step, &|_, y| y[0], Direction::Falling, 1e-12, 1e-12).is_none());
}

#[test]
fn invariant_physical_events_return_consistent_states() {
    let mass = 0.8;
    let horizon = horizon_event(mass, 7.0).unwrap();
    let collapse = collapse_event(mass, 7.0, 0.2).unwrap();
    assert!((horizon.state[0] - 2.0 * mass).abs() < 2e-9);
    assert!((collapse.state[0] - 0.2).abs() < 2e-9);
    assert!(horizon.t < collapse.t);
}

#[test]
fn deterministic_rerun_is_bitwise_equal() {
    let a = pressure_zero(0.731).unwrap();
    let b = pressure_zero(0.731).unwrap();
    assert_eq!(a.t.to_bits(), b.t.to_bits());
    assert_eq!(a.value.to_bits(), b.value.to_bits());
    assert_eq!(a.state[0].to_bits(), b.state[0].to_bits());
}
