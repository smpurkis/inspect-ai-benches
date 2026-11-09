mod francis;
mod hessenberg;
mod matrix;

use francis::{deflatable, francis_double_shift};
use hessenberg::hessenberg;
use matrix::Matrix;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;

fn real_schur(mut h: Matrix, mut q: Matrix) -> Result<(Matrix, Matrix), &'static str> {
    let n = h.n();
    if n < 2 { return Ok((h, q)); }
    let eps = f64::EPSILON;
    let safe_min = f64::MIN_POSITIVE / eps;
    let mut hi = n - 1;
    let mut iterations = 0usize;
    while hi > 0 {
        for i in 1..=hi {
            if deflatable(&h, i, eps, safe_min) { h[(i, i - 1)] = 0.0; }
        }
        if h[(hi, hi - 1)] == 0.0 {
            hi -= 1;
            iterations = 0;
            continue;
        }
        if hi == 1 || h[(hi - 1, hi - 2)] == 0.0 {
            hi = hi.saturating_sub(2);
            iterations = 0;
            continue;
        }
        let mut lo = 0;
        for i in (1..hi).rev() {
            if h[(i, i - 1)] == 0.0 { lo = i; break; }
        }
        francis_double_shift(&mut h, &mut q, lo, hi);
        for i in 2..n {
            for j in 0..i - 1 { h[(i, j)] = 0.0; }
        }
        iterations += 1;
        if iterations > 120 * (hi - lo + 1) { return Err("Francis QR iteration did not converge"); }
    }
    Ok((h, q))
}

#[pyfunction]
fn schur(py: Python<'_>, value: &PyAny) -> PyResult<PyObject> {
    let a = Matrix::from_python(value)?;
    if a.n() == 0 { return Err(PyValueError::new_err("matrix must be nonempty")); }
    let (h, q) = hessenberg(a);
    let (t, q) = real_schur(h, q).map_err(PyRuntimeError::new_err)?;
    Ok((t.to_python(py), q.to_python(py)).into_py(py))
}

#[pymodule]
fn rustlinalg(_py: Python<'_>, module: &PyModule) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(schur, module)?)?;
    Ok(())
}
