use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PySequence;
use std::ops::{Index, IndexMut};

#[derive(Clone, Debug)]
pub(crate) struct Matrix { n: usize, data: Vec<f64> }

impl Matrix {
    pub(crate) fn zeros(n: usize) -> Self { Self { n, data: vec![0.0; n * n] } }
    pub(crate) fn identity(n: usize) -> Self {
        let mut result = Self::zeros(n);
        for i in 0..n { result[(i, i)] = 1.0; }
        result
    }
    pub(crate) fn n(&self) -> usize { self.n }

    pub(crate) fn from_python(value: &PyAny) -> PyResult<Self> {
        if let Ok(dtype) = value.getattr("dtype") {
            if dtype.str()?.to_str()? != "float64" {
                return Err(PyValueError::new_err("expected a float64 matrix"));
            }
        }
        let owned;
        let rows = if let Ok(rows) = value.downcast::<PySequence>() {
            rows
        } else {
            owned = value.call_method0("tolist")?;
            owned.downcast::<PySequence>()?
        };
        let n = rows.len()? as usize;
        let mut result = Self::zeros(n);
        for i in 0..n {
            let row_obj = rows.get_item(i)?;
            let row = row_obj.downcast::<PySequence>()?;
            if row.len()? as usize != n {
                return Err(PyValueError::new_err("expected a square matrix"));
            }
            for j in 0..n {
                let x: f64 = row.get_item(j)?.extract()?;
                if !x.is_finite() { return Err(PyValueError::new_err("matrix entries must be finite")); }
                result[(i, j)] = x;
            }
        }
        Ok(result)
    }

    pub(crate) fn to_python(&self, py: Python<'_>) -> PyObject {
        (0..self.n).map(|i| (0..self.n).map(|j| self[(i, j)]).collect::<Vec<_>>())
            .collect::<Vec<_>>().into_py(py)
    }
}

impl Index<(usize, usize)> for Matrix {
    type Output = f64;
    fn index(&self, (i, j): (usize, usize)) -> &Self::Output { &self.data[i * self.n + j] }
}
impl IndexMut<(usize, usize)> for Matrix {
    fn index_mut(&mut self, (i, j): (usize, usize)) -> &mut Self::Output { &mut self.data[i * self.n + j] }
}
