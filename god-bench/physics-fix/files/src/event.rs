use crate::{DenseStep, Direction, EventHit};

/// Locate a directional zero inside one accepted dense-output step.
///
/// This starter only interpolates endpoint event values. It compiles and handles
/// trivial linear events, but it does not perform the required safeguarded
/// iteration over the supplied dense output.
pub fn localize_event<G>(
    step: &DenseStep,
    event: &G,
    direction: Direction,
    _time_tolerance: f64,
    value_tolerance: f64,
) -> Option<EventHit>
where
    G: Fn(f64, &[f64]) -> f64,
{
    let left_state = step.evaluate(step.start());
    let right_state = step.evaluate(step.end());
    let left = event(step.start(), &left_state);
    let right = event(step.end(), &right_state);
    let allowed = match direction {
        Direction::Any => left * right <= 0.0,
        Direction::Rising => left <= 0.0 && right >= 0.0,
        Direction::Falling => left >= 0.0 && right <= 0.0,
    };
    if !allowed || !left.is_finite() || !right.is_finite() {
        return None;
    }
    let t = if left.abs() <= value_tolerance {
        step.start()
    } else if right.abs() <= value_tolerance {
        step.end()
    } else {
        step.start() + (step.end() - step.start()) * left / (left - right)
    };
    let state = step.evaluate(t);
    Some(EventHit { t, value: event(t, &state), state })
}
