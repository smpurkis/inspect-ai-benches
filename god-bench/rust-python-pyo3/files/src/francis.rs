use crate::matrix::Matrix;

/// Decide whether h[i,i-1] can be set to zero without splitting a coupled block.
/// The starter criterion is intentionally incomplete: it uses an absolute test
/// and therefore fails for rescaled and near-underflow matrices.
pub(crate) fn deflatable(h: &Matrix, i: usize, eps: f64, _safe_min: f64) -> bool {
    h[(i, i - 1)].abs() <= eps
}

/// Perform one implicit real Francis double-shift sweep on lo..=hi, updating Q.
///
/// This compilable starter leaves the bulge chase unimplemented.
pub(crate) fn francis_double_shift(
    _h: &mut Matrix,
    _q: &mut Matrix,
    _lo: usize,
    _hi: usize,
) {
}
