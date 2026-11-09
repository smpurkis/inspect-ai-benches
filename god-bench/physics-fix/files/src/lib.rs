mod event;

pub use event::localize_event;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Direction {
    Any,
    Rising,
    Falling,
}

#[derive(Clone, Debug)]
pub struct EventHit {
    pub t: f64,
    pub state: Vec<f64>,
    pub value: f64,
}

#[derive(Clone, Debug)]
pub struct DenseStep {
    t0: f64,
    t1: f64,
    y0: Vec<f64>,
    y1: Vec<f64>,
    f0: Vec<f64>,
    f1: Vec<f64>,
}

impl DenseStep {
    pub fn from_endpoints(
        t0: f64,
        t1: f64,
        y0: Vec<f64>,
        y1: Vec<f64>,
        f0: Vec<f64>,
        f1: Vec<f64>,
    ) -> Self {
        assert!(t1 > t0 && y0.len() == y1.len());
        assert!(y0.len() == f0.len() && y0.len() == f1.len());
        Self { t0, t1, y0, y1, f0, f1 }
    }

    pub fn start(&self) -> f64 { self.t0 }
    pub fn end(&self) -> f64 { self.t1 }

    /// Cubic Hermite dense output supplied by the accepted RK45 step.
    pub fn evaluate(&self, t: f64) -> Vec<f64> {
        let h = self.t1 - self.t0;
        let s = ((t - self.t0) / h).clamp(0.0, 1.0);
        let h00 = (1.0 + 2.0 * s) * (1.0 - s) * (1.0 - s);
        let h10 = s * (1.0 - s) * (1.0 - s);
        let h01 = s * s * (3.0 - 2.0 * s);
        let h11 = s * s * (s - 1.0);
        (0..self.y0.len()).map(|i|
            h00 * self.y0[i] + h10 * h * self.f0[i]
                + h01 * self.y1[i] + h11 * h * self.f1[i]
        ).collect()
    }
}

fn combine(y: &[f64], h: f64, terms: &[(f64, &[f64])]) -> Vec<f64> {
    (0..y.len()).map(|i| {
        y[i] + h * terms.iter().map(|(a, k)| a * k[i]).sum::<f64>()
    }).collect()
}

/// One supplied Dormand-Prince 5(4) step and its dense interpolant.
pub fn rk45_dense<F>(f: &F, t: f64, y: &[f64], h: f64) -> (DenseStep, f64)
where F: Fn(f64, &[f64]) -> Vec<f64> {
    let k1 = f(t, y);
    let y2 = combine(y, h, &[(1.0 / 5.0, &k1)]);
    let k2 = f(t + h / 5.0, &y2);
    let y3 = combine(y, h, &[(3.0 / 40.0, &k1), (9.0 / 40.0, &k2)]);
    let k3 = f(t + 3.0 * h / 10.0, &y3);
    let y4 = combine(y, h, &[(44.0 / 45.0, &k1), (-56.0 / 15.0, &k2), (32.0 / 9.0, &k3)]);
    let k4 = f(t + 4.0 * h / 5.0, &y4);
    let y5s = combine(y, h, &[(19372.0 / 6561.0, &k1), (-25360.0 / 2187.0, &k2), (64448.0 / 6561.0, &k3), (-212.0 / 729.0, &k4)]);
    let k5 = f(t + 8.0 * h / 9.0, &y5s);
    let y6 = combine(y, h, &[(9017.0 / 3168.0, &k1), (-355.0 / 33.0, &k2), (46732.0 / 5247.0, &k3), (49.0 / 176.0, &k4), (-5103.0 / 18656.0, &k5)]);
    let k6 = f(t + h, &y6);
    let next = combine(y, h, &[(35.0 / 384.0, &k1), (500.0 / 1113.0, &k3), (125.0 / 192.0, &k4), (-2187.0 / 6784.0, &k5), (11.0 / 84.0, &k6)]);
    let k7 = f(t + h, &next);
    let fourth = combine(y, h, &[(5179.0 / 57600.0, &k1), (7571.0 / 16695.0, &k3), (393.0 / 640.0, &k4), (-92097.0 / 339200.0, &k5), (187.0 / 2100.0, &k6), (1.0 / 40.0, &k7)]);
    let error = next.iter().zip(&fourth).map(|(a, b)| (a - b).abs()).fold(0.0, f64::max);
    (DenseStep::from_endpoints(t, t + h, y.to_vec(), next, k1, k7), error)
}

pub fn integrate_until<F, G>(
    rhs: F,
    event: G,
    direction: Direction,
    t0: f64,
    y0: Vec<f64>,
    t_bound: f64,
    initial_step: f64,
) -> Option<EventHit>
where
    F: Fn(f64, &[f64]) -> Vec<f64>,
    G: Fn(f64, &[f64]) -> f64,
{
    let mut t = t0;
    let mut y = y0;
    let mut h = initial_step.min(t_bound - t0);
    while t < t_bound {
        h = h.min(t_bound - t);
        let (step, error) = rk45_dense(&rhs, t, &y, h);
        let next = step.evaluate(step.end());
        let scale = y.iter().chain(next.iter()).map(|v| v.abs()).fold(1.0, f64::max);
        let tolerance = 1e-11 + 1e-9 * scale;
        if error > tolerance {
            h *= (0.9 * (tolerance / error).powf(0.2)).clamp(0.1, 0.5);
            continue;
        }
        if let Some(hit) = localize_event(&step, &event, direction, 1e-11, 1e-12) {
            return Some(hit);
        }
        t = step.end();
        y = next;
        let factor = if error == 0.0 { 2.0 } else { (0.9 * (tolerance / error).powf(0.2)).clamp(0.5, 2.0) };
        h *= factor;
    }
    None
}

pub fn pressure_zero(central_pressure: f64) -> Option<EventHit> {
    integrate_until(|r, _| vec![-2.0 * r], |_, y| y[0], Direction::Falling,
        0.0, vec![central_pressure], 4.0 * central_pressure.sqrt().max(1.0), 0.37)
}

pub fn collapse_event(mass: f64, initial_radius: f64, cutoff: f64) -> Option<EventHit> {
    integrate_until(|_, y| vec![-(2.0 * mass / y[0].max(cutoff * 0.1)).sqrt()],
        move |_, y| y[0] - cutoff, Direction::Falling, 0.0, vec![initial_radius],
        2.0 * initial_radius.powf(1.5) / (2.0 * mass).sqrt(), 0.071)
}

pub fn horizon_event(mass: f64, initial_radius: f64) -> Option<EventHit> {
    collapse_event(mass, initial_radius, 2.0 * mass)
}
