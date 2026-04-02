//! rustlinalg — pure Rust linear algebra exposed to Python via PyO3.
//!
//! Constraints (enforced by tests):
//! - Only pyo3 and ndarray dependencies are allowed.
//! - Do not import Python numpy/scipy from Rust.
//! - Return values may be plain Python lists/floats (NumPy will convert).
//!
//! Implemented functions:
//! - matmul(A, B) -> A @ B
//! - cholesky(A) -> lower-triangular L s.t. A = L L^T (A must be SPD)
//! - solve_spd(A, b) -> x solving Ax = b using the Cholesky factorization
//! - norm2(x) -> Euclidean 2-norm of vector x
//! - qr(A) -> (Q, R) Householder QR with complete Q (m x m) and R (m x n)
//! - eig_symmetric(A) -> (eigenvalues, eigenvectors) for symmetric A
//! - svd(A) -> (U, s, Vt) with full matrices where U is m x m and Vt is n x n
//! - matrix_exp(A) -> expm(A) via scaling-and-squaring with Taylor series
//! - solve_lstsq(A, b) -> least-squares solution using normal equations
//! - real_schur(A) -> (Q, T) real Schur form via orthogonal iteration
//! - solve_care(A, B, Q, R) -> stabilizing CARE solution via matrix sign iteration
//!
//! The implementations below are intentionally self-contained and rely only
//! on standard Rust and small helper routines. Performance is adequate for
//! the matrix sizes used in the tests.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

// ---------- Basic helpers: Python <-> Rust conversions ----------

fn to_real_scalar(obj: &PyAny, err: &str) -> PyResult<f64> {
    if obj.extract::<&pyo3::types::PyComplex>().is_ok() {
        return Err(PyValueError::new_err(err.to_string()));
    }
    obj.extract::<f64>()
        .map_err(|_| PyValueError::new_err(err.to_string()))
}

fn to_vec1(obj: &PyAny) -> PyResult<Vec<f64>> {
    let seq = obj
        .iter()
        .map_err(|_| PyValueError::new_err("Expected a 1D real-valued array"))?;
    let mut out = Vec::new();
    for item in seq {
        let item = item
            .map_err(|_| PyValueError::new_err("Expected a 1D real-valued array"))?;
        let v = to_real_scalar(item, "Expected a 1D real-valued array")?;
        out.push(v);
    }
    Ok(out)
}

fn to_vec2(obj: &PyAny) -> PyResult<Vec<Vec<f64>>> {
    let seq = obj
        .iter()
        .map_err(|_| PyValueError::new_err("Expected a 2D real-valued array"))?;
    let mut out: Vec<Vec<f64>> = Vec::new();
    for row in seq {
        let row = row
            .map_err(|_| PyValueError::new_err("Expected a 2D real-valued array"))?;
        out.push(to_vec1(row)?);
    }
    // Basic shape validation: all rows equal length
    if let Some(first) = out.first() {
        let n = first.len();
        if n == 0 {
            return Err(PyValueError::new_err("Matrix must have non-empty rows"));
        }
        for r in &out {
            if r.len() != n {
                return Err(PyValueError::new_err(
                    "All rows of the matrix must have the same length",
                ));
            }
        }
    } else {
        return Err(PyValueError::new_err("Empty matrix is not supported"));
    }
    Ok(out)
}

fn vec2_shape(a: &Vec<Vec<f64>>) -> (usize, usize) {
    (a.len(), a[0].len())
}

// ---------- Linear algebra primitives on Vec<Vec<f64>> ----------

fn zeros(m: usize, n: usize) -> Vec<Vec<f64>> {
    vec![vec![0.0; n]; m]
}

fn identity(n: usize) -> Vec<Vec<f64>> {
    let mut i = zeros(n, n);
    for k in 0..n {
        i[k][k] = 1.0;
    }
    i
}

fn transpose(a: &Vec<Vec<f64>>) -> Vec<Vec<f64>> {
    let (m, n) = vec2_shape(a);
    let mut t = zeros(n, m);
    for i in 0..m {
        for j in 0..n {
            t[j][i] = a[i][j];
        }
    }
    t
}

fn matmul_rr(a: &Vec<Vec<f64>>, b: &Vec<Vec<f64>>) -> Vec<Vec<f64>> {
    let (m, k1) = vec2_shape(a);
    let (k2, n) = vec2_shape(b);
    assert_eq!(k1, k2, "Inner dimensions must match for matmul");
    let mut c = zeros(m, n);
    for i in 0..m {
        for k in 0..k1 {
            let aik = a[i][k];
            if aik != 0.0 {
                for j in 0..n {
                    c[i][j] += aik * b[k][j];
                }
            }
        }
    }
    c
}

fn matvec(a: &Vec<Vec<f64>>, x: &Vec<f64>) -> Vec<f64> {
    let (m, n) = vec2_shape(a);
    assert_eq!(n, x.len());
    let mut y = vec![0.0; m];
    for i in 0..m {
        let mut s = 0.0;
        for j in 0..n {
            s += a[i][j] * x[j];
        }
        y[i] = s;
    }
    y
}

fn dot(x: &[f64], y: &[f64]) -> f64 {
    x.iter().zip(y.iter()).map(|(a, b)| a * b).sum()
}

fn vector_norm2(x: &[f64]) -> f64 {
    x.iter().map(|v| v * v).sum::<f64>().sqrt()
}

fn one_norm(a: &Vec<Vec<f64>>) -> f64 {
    let (m, n) = vec2_shape(a);
    let mut max_sum = 0.0;
    for j in 0..n {
        let mut s = 0.0;
        for i in 0..m {
            s += a[i][j].abs();
        }
        if s > max_sum {
            max_sum = s;
        }
    }
    max_sum
}

fn add(a: &Vec<Vec<f64>>, b: &Vec<Vec<f64>>) -> Vec<Vec<f64>> {
    let (m, n) = vec2_shape(a);
    let mut c = zeros(m, n);
    for i in 0..m {
        for j in 0..n {
            c[i][j] = a[i][j] + b[i][j];
        }
    }
    c
}

fn sub(a: &Vec<Vec<f64>>, b: &Vec<Vec<f64>>) -> Vec<Vec<f64>> {
    let (m, n) = vec2_shape(a);
    let mut c = zeros(m, n);
    for i in 0..m {
        for j in 0..n {
            c[i][j] = a[i][j] - b[i][j];
        }
    }
    c
}

fn scale(a: &Vec<Vec<f64>>, alpha: f64) -> Vec<Vec<f64>> {
    let (m, n) = vec2_shape(a);
    let mut c = zeros(m, n);
    for i in 0..m {
        for j in 0..n {
            c[i][j] = alpha * a[i][j];
        }
    }
    c
}

// ---------- Cholesky (lower) and SPD solves ----------

fn cholesky_lower(a: &Vec<Vec<f64>>) -> PyResult<Vec<Vec<f64>>> {
    let (n, n2) = vec2_shape(a);
    if n != n2 {
        return Err(PyValueError::new_err("cholesky expects a square matrix"));
    }
    let mut l = zeros(n, n);
    for i in 0..n {
        for j in 0..=i {
            let mut sum = a[i][j];
            for k in 0..j {
                sum -= l[i][k] * l[j][k];
            }
            if i == j {
                if sum <= 0.0 {
                    return Err(PyValueError::new_err(
                        "Matrix is not symmetric positive definite",
                    ));
                }
                l[i][j] = sum.sqrt();
            } else {
                l[i][j] = sum / l[j][j];
            }
        }
    }
    Ok(l)
}

fn forward_subst(l: &Vec<Vec<f64>>, b: &Vec<f64>) -> Vec<f64> {
    let n = l.len();
    let mut y = vec![0.0; n];
    for i in 0..n {
        let mut sum = b[i];
        for k in 0..i {
            sum -= l[i][k] * y[k];
        }
        y[i] = sum / l[i][i];
    }
    y
}

fn backward_subst_ut(u: &Vec<Vec<f64>>, y: &Vec<f64>) -> Vec<f64> {
    let n = u.len();
    let mut x = vec![0.0; n];
    for i in (0..n).rev() {
        let mut sum = y[i];
        for k in (i + 1)..n {
            sum -= u[i][k] * x[k];
        }
        x[i] = sum / u[i][i];
    }
    x
}

// ---------- QR via Householder reflections (complete Q) ----------

fn qr_householder_complete(a: &Vec<Vec<f64>>) -> (Vec<Vec<f64>>, Vec<Vec<f64>>) {
    let (m, n) = vec2_shape(a);
    let mut r = a.clone();
    let mut q = identity(m);
    let kmax = m.min(n);
    for k in 0..kmax {
        // Build Householder to zero out entries below r[k][k] in column k
        let mut x = vec![0.0; m - k];
        for i in 0..(m - k) {
            x[i] = r[k + i][k];
        }
        let normx = vector_norm2(&x);
        if normx == 0.0 {
            continue;
        }
        let sign = if x[0] >= 0.0 { 1.0 } else { -1.0 };
        let mut v = x.clone();
        v[0] += sign * normx;
        let vnorm = vector_norm2(&v);
        if vnorm == 0.0 {
            continue;
        }
        for i in 0..v.len() {
            v[i] /= vnorm;
        }
        // Apply H = I - 2 v v^T to r (on the left), only rows k..m
        for j in k..n {
            let mut s = 0.0;
            for i in 0..(m - k) {
                s += v[i] * r[k + i][j];
            }
            s *= 2.0;
            for i in 0..(m - k) {
                r[k + i][j] -= s * v[i];
            }
        }
        // Accumulate Q = Q * H
        for j in 0..m {
            let mut s = 0.0;
            for i in 0..(m - k) {
                s += v[i] * q[j][k + i];
            }
            s *= 2.0;
            for i in 0..(m - k) {
                q[j][k + i] -= s * v[i];
            }
        }
    }
    (q, r)
}

// ---------- Symmetric eigendecomposition via Jacobi rotations ----------

fn eig_symmetric_jacobi(a: &Vec<Vec<f64>>) -> (Vec<f64>, Vec<Vec<f64>>) {
    let (n, n2) = vec2_shape(a);
    assert_eq!(n, n2);
    let mut a_mat = a.clone();
    let mut v = identity(n);
    let mut changed = true;
    let mut iter = 0usize;
    let max_iter = 100 * n * n;
    while changed && iter < max_iter {
        changed = false;
        iter += 1;
        for p in 0..n - 1 {
            for q in (p + 1)..n {
                let apq = a_mat[p][q];
                if apq.abs() < 1e-15 {
                    continue;
                }
                let app = a_mat[p][p];
                let aqq = a_mat[q][q];
                let tau = (aqq - app) / (2.0 * apq);
                let t = if tau >= 0.0 {
                    1.0 / (tau + (1.0 + tau * tau).sqrt())
                } else {
                    -1.0 / (-tau + (1.0 + tau * tau).sqrt())
                };
                let c = 1.0 / (1.0 + t * t).sqrt();
                let s = t * c;
                // Update A = J^T A J (only affected rows/cols)
                for k in 0..n {
                    let aik = a_mat[p][k];
                    let aqk = a_mat[q][k];
                    a_mat[p][k] = c * aik - s * aqk;
                    a_mat[q][k] = s * aik + c * aqk;
                }
                for k in 0..n {
                    let akp = a_mat[k][p];
                    let akq = a_mat[k][q];
                    a_mat[k][p] = c * akp - s * akq;
                    a_mat[k][q] = s * akp + c * akq;
                }
                // Accumulate V = V J
                for k in 0..n {
                    let vkp = v[k][p];
                    let vkq = v[k][q];
                    v[k][p] = c * vkp - s * vkq;
                    v[k][q] = s * vkp + c * vkq;
                }
                if apq.abs() > 1e-15 {
                    changed = true;
                }
            }
        }
        // Check convergence: off-diagonal Frobenius norm small
        let mut off = 0.0;
        for i in 0..n {
            for j in 0..n {
                if i != j {
                    off += a_mat[i][j] * a_mat[i][j];
                }
            }
        }
        if off.sqrt() < 1e-12 {
            break;
        }
    }
    // Extract eigenvalues (diagonal of a_mat) and sort ascending
    let mut evals: Vec<(f64, usize)> = (0..n).map(|i| (a_mat[i][i], i)).collect();
    evals.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap());
    let mut d = vec![0.0; n];
    let mut evecs = zeros(n, n);
    for (new_idx, (_val, old_idx)) in evals.iter().enumerate() {
        d[new_idx] = a_mat[*old_idx][*old_idx];
        for r in 0..n {
            evecs[r][new_idx] = v[r][*old_idx];
        }
    }
    (d, evecs)
}

// ---------- Orthonormalization helpers ----------

fn mgs_orthonormalize(columns: &mut Vec<Vec<f64>>) {
    // Modified Gram-Schmidt in-place on column vectors (same length)
    let m = columns[0].len();
    for j in 0..columns.len() {
        for i in 0..j {
            let r = dot(&columns[i], &columns[j]);
            for k in 0..m {
                columns[j][k] -= r * columns[i][k];
            }
        }
        let norm = vector_norm2(&columns[j]);
        if norm > 0.0 {
            for k in 0..m {
                columns[j][k] /= norm;
            }
        }
    }
}

fn complete_orthonormal_basis(existing: &mut Vec<Vec<f64>>, m: usize) {
    // existing: list of m-length orthonormal column vectors; add more from
    // canonical basis e_i as needed to reach m vectors.
    let mut i = 0usize;
    while existing.len() < m && i < m {
        let mut v = vec![0.0; m];
        v[i] = 1.0;
        // Orthogonalize against existing
        for u in existing.iter() {
            let r = dot(u, &v);
            for k in 0..m {
                v[k] -= r * u[k];
            }
        }
        let nrm = vector_norm2(&v);
        if nrm > 1e-12 {
            for k in 0..m {
                v[k] /= nrm;
            }
            existing.push(v);
        }
        i += 1;
    }
}

// ---------- SVD via symmetric eigen-decomposition ----------

fn svd_via_eig(a: &Vec<Vec<f64>>) -> (Vec<Vec<f64>>, Vec<f64>, Vec<Vec<f64>>) {
    let (m, n) = vec2_shape(a);
    let r = m.min(n);
    if m >= n {
        // V from eigen-decomposition of A^T A (n x n)
        let at = transpose(a);
        let ata = matmul_rr(&at, a);
        let (mut evals, mut v) = eig_symmetric_jacobi(&ata);
        // evals currently ascending; reverse to descending
        let mut order: Vec<usize> = (0..n).collect();
        order.sort_by(|&i, &j| evals[j].partial_cmp(&evals[i]).unwrap());
        let mut s = vec![0.0; r];
        let mut v_sorted = zeros(n, n);
        let evals_old = evals.clone();
        for new_idx in 0..n {
            let old_idx = order[new_idx];
            for i in 0..n {
                v_sorted[i][new_idx] = v[i][old_idx];
            }
            evals[new_idx] = evals_old[old_idx];
        }
        for i in 0..r {
            s[i] = evals[i].max(0.0).sqrt();
        }
        v = v_sorted;
        // U_partial = A V_r Sigma^{-1}
        let mut cols_u: Vec<Vec<f64>> = Vec::new();
        for i in 0..r {
            let sigma = s[i];
            if sigma > 0.0 {
                let mut v_i = vec![0.0; n];
                for k in 0..n {
                    v_i[k] = v[k][i];
                }
                let av = matvec(a, &v_i);
                let u_i = av.iter().map(|&val| val / sigma).collect::<Vec<_>>();
                // store column
                cols_u.push(u_i);
            } else {
                // Zero singular value: skip column; will be completed later
            }
        }
        if !cols_u.is_empty() {
            mgs_orthonormalize(&mut cols_u);
        }
        complete_orthonormal_basis(&mut cols_u, m);
        // assemble U from columns
        let mut u = zeros(m, m);
        for j in 0..m {
            for i in 0..m {
                u[i][j] = cols_u[j][i];
            }
        }
        let vt = transpose(&v);
        (u, s, vt)
    } else {
        // U from eigen-decomposition of A A^T (m x m)
        let aat = matmul_rr(a, &transpose(a));
        let (mut evals, mut u) = eig_symmetric_jacobi(&aat);
        // sort descending
        let mut order: Vec<usize> = (0..m).collect();
        order.sort_by(|&i, &j| evals[j].partial_cmp(&evals[i]).unwrap());
        let mut s = vec![0.0; r];
        let mut u_sorted = zeros(m, m);
        let evals_old = evals.clone();
        for new_idx in 0..m {
            let old_idx = order[new_idx];
            for i in 0..m {
                u_sorted[i][new_idx] = u[i][old_idx];
            }
            evals[new_idx] = evals_old[old_idx];
        }
        for i in 0..r {
            s[i] = evals[i].max(0.0).sqrt();
        }
        u = u_sorted;
        // V_partial = A^T U_r Sigma^{-1}
        let at = transpose(a);
        let mut cols_v: Vec<Vec<f64>> = Vec::new();
        for i in 0..r {
            let sigma = s[i];
            if sigma > 0.0 {
                let mut u_i = vec![0.0; m];
                for k in 0..m {
                    u_i[k] = u[k][i];
                }
                let atu = matvec(&at, &u_i);
                let v_i = atu.iter().map(|&val| val / sigma).collect::<Vec<_>>();
                cols_v.push(v_i);
            } else {
                // Skip zero singular value; will complete basis
            }
        }
        if !cols_v.is_empty() {
            mgs_orthonormalize(&mut cols_v);
        }
        complete_orthonormal_basis(&mut cols_v, n);
        // assemble V from columns
        let mut v = zeros(n, n);
        for j in 0..n {
            for i in 0..n {
                v[i][j] = cols_v[j][i];
            }
        }
        let vt = transpose(&v);
        (u, s, vt)
    }
}

// ---------- Matrix exponential via scaling and squaring (Taylor) ----------

fn matrix_exp_scaling_taylor(a: &Vec<Vec<f64>>) -> Vec<Vec<f64>> {
    let (n, n2) = vec2_shape(a);
    assert_eq!(n, n2);
    let norm = one_norm(a);
    let theta = 0.5f64; // scale so that ||A||_1 / 2^s <= theta
    let mut s = 0usize;
    if norm > theta {
        let ratio = norm / theta;
        s = ratio.log2().ceil().max(0.0) as usize;
    }
    let mut b = a.clone();
    if s > 0 {
        let scale_factor = 2f64.powi(-(s as i32));
        b = scale(a, scale_factor);
    }
    // Taylor series exp(B) ~ sum_{k=0..K} B^k / k!
    let k_max = 32usize; // sufficient for scaled B
    let mut result = identity(n);
    let mut term = identity(n); // B^0 / 0! = I
    for k in 1..=k_max {
        term = matmul_rr(&term, &b);
        let coeff = 1.0 / (1..=k).fold(1.0, |acc, v| acc * (v as f64));
        let add_term = scale(&term, coeff);
        result = add(&result, &add_term);
    }
    // Squaring: exp(A) = (exp(B))^(2^s)
    for _ in 0..s {
        result = matmul_rr(&result, &result);
    }
    result
}



// ---------- General matrix helpers for advanced Step 3 routines ----------

fn fro_norm(a: &Vec<Vec<f64>>) -> f64 {
    let (m, n) = vec2_shape(a);
    let mut sum = 0.0;
    for i in 0..m {
        for j in 0..n {
            sum += a[i][j] * a[i][j];
        }
    }
    sum.sqrt()
}

fn max_abs_below_first_subdiag(a: &Vec<Vec<f64>>) -> f64 {
    let (m, n) = vec2_shape(a);
    let mut max_val = 0.0;
    for i in 0..m {
        let upto = i.saturating_sub(1).min(n);
        for j in 0..upto {
            let val = a[i][j].abs();
            if val > max_val {
                max_val = val;
            }
        }
    }
    max_val
}

fn is_symmetric(a: &Vec<Vec<f64>>, tol: f64) -> bool {
    let (n, n2) = vec2_shape(a);
    if n != n2 {
        return false;
    }
    for i in 0..n {
        for j in 0..i {
            if (a[i][j] - a[j][i]).abs() > tol {
                return false;
            }
        }
    }
    true
}

fn invert_matrix(a: &Vec<Vec<f64>>) -> PyResult<Vec<Vec<f64>>> {
    let (n, n2) = vec2_shape(a);
    if n != n2 {
        return Err(PyValueError::new_err(
            "matrix inverse expects a square matrix",
        ));
    }
    let mut aug = zeros(n, 2 * n);
    for i in 0..n {
        for j in 0..n {
            aug[i][j] = a[i][j];
        }
        aug[i][n + i] = 1.0;
    }
    for col in 0..n {
        let mut pivot = col;
        let mut pivot_abs = aug[col][col].abs();
        for row in (col + 1)..n {
            let cand = aug[row][col].abs();
            if cand > pivot_abs {
                pivot = row;
                pivot_abs = cand;
            }
        }
        if pivot_abs < 1e-14 {
            return Err(PyValueError::new_err(
                "matrix is singular to working precision",
            ));
        }
        if pivot != col {
            aug.swap(pivot, col);
        }
        let piv = aug[col][col];
        for j in col..(2 * n) {
            aug[col][j] /= piv;
        }
        for row in 0..n {
            if row == col {
                continue;
            }
            let factor = aug[row][col];
            if factor == 0.0 {
                continue;
            }
            for j in col..(2 * n) {
                aug[row][j] -= factor * aug[col][j];
            }
        }
    }
    let mut inv = zeros(n, n);
    for i in 0..n {
        for j in 0..n {
            inv[i][j] = aug[i][n + j];
        }
    }
    Ok(inv)
}

fn matrix_from_columns(cols: &Vec<Vec<f64>>) -> Vec<Vec<f64>> {
    let m = cols[0].len();
    let n = cols.len();
    let mut out = zeros(m, n);
    for j in 0..n {
        for i in 0..m {
            out[i][j] = cols[j][i];
        }
    }
    out
}

fn top_rows(a: &Vec<Vec<f64>>, rows: usize) -> Vec<Vec<f64>> {
    let (_, n) = vec2_shape(a);
    let mut out = zeros(rows, n);
    for i in 0..rows {
        for j in 0..n {
            out[i][j] = a[i][j];
        }
    }
    out
}

fn bottom_rows(a: &Vec<Vec<f64>>, start: usize) -> Vec<Vec<f64>> {
    let (m, n) = vec2_shape(a);
    let rows = m - start;
    let mut out = zeros(rows, n);
    for i in 0..rows {
        for j in 0..n {
            out[i][j] = a[start + i][j];
        }
    }
    out
}

fn orthogonalize_against(v: &mut Vec<f64>, basis: &Vec<Vec<f64>>) {
    for u in basis {
        let coeff = dot(u, v);
        for k in 0..v.len() {
            v[k] -= coeff * u[k];
        }
    }
}

fn projector_range_basis(projector: &Vec<Vec<f64>>, target_cols: usize) -> PyResult<Vec<Vec<f64>>> {
    let (m, m2) = vec2_shape(projector);
    if m != m2 {
        return Err(PyValueError::new_err("projector must be square"));
    }
    let mut cols: Vec<Vec<f64>> = Vec::new();
    for j in 0..m {
        let mut v = vec![0.0; m];
        for i in 0..m {
            v[i] = projector[i][j];
        }
        orthogonalize_against(&mut v, &cols);
        let norm = vector_norm2(&v);
        if norm > 1e-8 {
            for k in 0..m {
                v[k] /= norm;
            }
            cols.push(v);
            if cols.len() == target_cols {
                return Ok(cols);
            }
        }
    }
    for j in 0..m {
        let mut v = vec![0.0; m];
        v[j] = 1.0;
        orthogonalize_against(&mut v, &cols);
        let norm = vector_norm2(&v);
        if norm > 1e-8 {
            for k in 0..m {
                v[k] /= norm;
            }
            cols.push(v);
            if cols.len() == target_cols {
                return Ok(cols);
            }
        }
    }
    Err(PyValueError::new_err("failed to find n stable eigenvalues"))
}

fn real_schur_orthogonal_iteration(a: &Vec<Vec<f64>>) -> PyResult<(Vec<Vec<f64>>, Vec<Vec<f64>>)> {
    let (n, n2) = vec2_shape(a);
    if n != n2 {
        return Err(PyValueError::new_err("real_schur expects a square matrix"));
    }
    let mut q_current = identity(n);
    let check_every = 25usize;
    let max_iter = if n <= 2 { 64usize } else { 3000usize };
    let mut t = a.clone();
    let mut best_q = q_current.clone();
    let mut best_t = t.clone();
    let mut best_score = f64::INFINITY;
    for iter in 0..max_iter {
        let z = matmul_rr(a, &q_current);
        let (q_next, _) = qr_householder_complete(&z);
        q_current = q_next;
        if iter + 1 == max_iter || (iter + 1) % check_every == 0 {
            let qt = transpose(&q_current);
            t = matmul_rr(&qt, &matmul_rr(a, &q_current));
            let lower = max_abs_below_first_subdiag(&t);
            let mut penalty = 0.0;
            let mut i = 0usize;
            while i + 1 < n {
                if t[i + 1][i].abs() > 1e-10 {
                    let a11 = t[i][i];
                    let a12 = t[i][i + 1];
                    let a21 = t[i + 1][i];
                    let a22 = t[i + 1][i + 1];
                    let disc = (a11 - a22) * (a11 - a22) + 4.0 * a12 * a21;
                    if disc > 0.0 {
                        penalty += disc;
                    }
                    i += 2;
                } else {
                    i += 1;
                }
            }
            let score = lower + penalty.sqrt();
            if score < best_score {
                best_score = score;
                best_q = q_current.clone();
                best_t = t.clone();
            }
            if lower < 1e-12 && penalty < 1e-10 {
                break;
            }
        }
    }
    let qt = transpose(&best_q);
    t = matmul_rr(&qt, &matmul_rr(a, &best_q));
    for i in 0..n {
        let upto = i.saturating_sub(1);
        for j in 0..upto {
            if t[i][j].abs() < 1e-14 {
                t[i][j] = 0.0;
            }
        }
    }
    Ok((best_q, t))
}

fn max_real_part_from_quasi_upper(t: &Vec<Vec<f64>>) -> f64 {
    let n = t.len();
    if n == 0 {
        return 0.0;
    }
    let mut max_real = f64::NEG_INFINITY;
    let mut i = 0usize;
    while i < n {
        if i + 1 < n && t[i + 1][i].abs() > 1e-10 {
            let real = 0.5 * (t[i][i] + t[i + 1][i + 1]);
            if real > max_real {
                max_real = real;
            }
            i += 2;
        } else {
            if t[i][i] > max_real {
                max_real = t[i][i];
            }
            i += 1;
        }
    }
    max_real
}

fn solve_care_matrix_sign(
    a: &Vec<Vec<f64>>,
    b: &Vec<Vec<f64>>,
    q: &Vec<Vec<f64>>,
    r: &Vec<Vec<f64>>,
) -> PyResult<Vec<Vec<f64>>> {
    let (n, n2) = vec2_shape(a);
    if n != n2 {
        return Err(PyValueError::new_err("A must be square"));
    }
    let (b_rows, m_inputs) = vec2_shape(b);
    if b_rows != n {
        return Err(PyValueError::new_err("B must have the same row count as A"));
    }
    let (q_rows, q_cols) = vec2_shape(q);
    if q_rows != n || q_cols != n {
        return Err(PyValueError::new_err("Q must be square and match A"));
    }
    let (r_rows, r_cols) = vec2_shape(r);
    if r_rows != m_inputs || r_cols != m_inputs {
        return Err(PyValueError::new_err("R must be square and match the control dimension"));
    }
    if !is_symmetric(q, 1e-10) {
        return Err(PyValueError::new_err("Q must be symmetric"));
    }
    if !is_symmetric(r, 1e-10) {
        return Err(PyValueError::new_err("R must be symmetric"));
    }
    let _r_chol = cholesky_lower(r)?;
    let rinv = invert_matrix(r)?;
    let bt = transpose(b);
    let g = matmul_rr(&matmul_rr(b, &rinv), &bt);

    let at = transpose(a);
    let mut h = zeros(2 * n, 2 * n);
    for i in 0..n {
        for j in 0..n {
            h[i][j] = a[i][j];
            h[i][n + j] = -g[i][j];
            h[n + i][j] = -q[i][j];
            h[n + i][n + j] = -at[i][j];
        }
    }

    let alpha = one_norm(&h).max(1.0);
    let mut s = scale(&h, 1.0 / alpha);
    let ident = identity(2 * n);
    for _ in 0..100 {
        let s_inv = invert_matrix(&s)?;
        let next = scale(&add(&s, &s_inv), 0.5);
        let diff = fro_norm(&sub(&next, &s));
        s = next;
        if diff < 1e-12 {
            break;
        }
    }

    let projector = scale(&sub(&ident, &s), 0.5);
    let basis = projector_range_basis(&projector, n)?;
    let u = matrix_from_columns(&basis);
    let u1 = top_rows(&u, n);
    let u2 = bottom_rows(&u, n);
    let u1_inv = invert_matrix(&u1)
        .map_err(|_| PyValueError::new_err("failed to find n stable eigenvalues"))?;
    let mut x = matmul_rr(&u2, &u1_inv);
    x = scale(&add(&x, &transpose(&x)), 0.5);

    let residual = add(
        &sub(
            &add(&matmul_rr(&at, &x), &matmul_rr(&x, a)),
            &matmul_rr(&matmul_rr(&x, &g), &x),
        ),
        q,
    );
    if fro_norm(&residual) > 1e-7 {
        return Err(PyValueError::new_err(
            "failed to find stabilizing CARE solution",
        ));
    }
    let closed_loop = sub(a, &matmul_rr(&g, &x));
    let (_, t_closed) = real_schur_orthogonal_iteration(&closed_loop)?;
    if max_real_part_from_quasi_upper(&t_closed) >= -1e-8 {
        return Err(PyValueError::new_err(
            "failed to find stabilizing CARE solution",
        ));
    }
    Ok(x)
}

// ---------- Python-callable wrappers ----------

#[pyfunction]
fn matmul(py_a: &PyAny, py_b: &PyAny) -> PyResult<Vec<Vec<f64>>> {
    let a = to_vec2(py_a)?;
    let b = to_vec2(py_b)?;
    let (m, k1) = vec2_shape(&a);
    let (k2, n) = vec2_shape(&b);
    if k1 != k2 {
        return Err(PyValueError::new_err("Inner dimensions must match"));
    }
    Ok(matmul_rr(&a, &b))
}

#[pyfunction]
fn cholesky(py_a: &PyAny) -> PyResult<Vec<Vec<f64>>> {
    let a = to_vec2(py_a)?;
    cholesky_lower(&a)
}

#[pyfunction]
fn solve_spd(py_a: &PyAny, py_b: &PyAny) -> PyResult<Vec<f64>> {
    let a = to_vec2(py_a)?;
    let b = to_vec1(py_b)?;
    let (n, n2) = vec2_shape(&a);
    if n != n2 {
        return Err(PyValueError::new_err("A must be square"));
    }
    if b.len() != n {
        return Err(PyValueError::new_err("Dimension mismatch in solve_spd"));
    }
    let l = cholesky_lower(&a)?;
    let y = forward_subst(&l, &b);
    let lt = transpose(&l);
    Ok(backward_subst_ut(&lt, &y))
}

#[pyfunction]
fn norm2(py_x: &PyAny) -> PyResult<f64> {
    let x = to_vec1(py_x)?;
    Ok(vector_norm2(&x))
}

#[pyfunction]
fn qr(py_a: &PyAny) -> PyResult<(Vec<Vec<f64>>, Vec<Vec<f64>>)> {
    let a = to_vec2(py_a)?;
    let (q, r) = qr_householder_complete(&a);
    Ok((q, r))
}

#[pyfunction]
fn eig_symmetric(py_a: &PyAny) -> PyResult<(Vec<f64>, Vec<Vec<f64>>)> {
    let a = to_vec2(py_a)?;
    let (n, n2) = vec2_shape(&a);
    if n != n2 {
        return Err(PyValueError::new_err(
            "eig_symmetric expects a square symmetric matrix",
        ));
    }
    // The Jacobi method assumes symmetry; no explicit symmetry check here
    let (vals, vecs) = eig_symmetric_jacobi(&a);
    Ok((vals, vecs))
}

#[pyfunction]
fn svd(py_a: &PyAny) -> PyResult<(Vec<Vec<f64>>, Vec<f64>, Vec<Vec<f64>>)> {
    let a = to_vec2(py_a)?;
    let (u, s, vt) = svd_via_eig(&a);
    Ok((u, s, vt))
}

#[pyfunction]
fn matrix_exp(py_a: &PyAny) -> PyResult<Vec<Vec<f64>>> {
    let a = to_vec2(py_a)?;
    let (n, n2) = vec2_shape(&a);
    if n != n2 {
        return Err(PyValueError::new_err("matrix_exp expects a square matrix"));
    }
    Ok(matrix_exp_scaling_taylor(&a))
}

#[pyfunction]
fn solve_lstsq(py_a: &PyAny, py_b: &PyAny) -> PyResult<Vec<f64>> {
    let a = to_vec2(py_a)?;
    let b = to_vec1(py_b)?;
    let (m, n) = vec2_shape(&a);
    if b.len() != m {
        return Err(PyValueError::new_err("Dimension mismatch in solve_lstsq"));
    }
    // Normal equations: (A^T A) x = A^T b
    let at = transpose(&a);
    let ata = matmul_rr(&at, &a);
    let atb = matvec(&at, &b);
    let l = cholesky_lower(&ata)?;
    let y = forward_subst(&l, &atb);
    let lt = transpose(&l);
    Ok(backward_subst_ut(&lt, &y))
}



#[pyfunction]
fn real_schur(py_a: &PyAny) -> PyResult<(Vec<Vec<f64>>, Vec<Vec<f64>>)> {
    let a = to_vec2(py_a)?;
    real_schur_orthogonal_iteration(&a)
}

#[pyfunction]
fn solve_care(py_a: &PyAny, py_b: &PyAny, py_q: &PyAny, py_r: &PyAny) -> PyResult<Vec<Vec<f64>>> {
    let a = to_vec2(py_a)?;
    let b = to_vec2(py_b)?;
    let q = to_vec2(py_q)?;
    let r = to_vec2(py_r)?;
    solve_care_matrix_sign(&a, &b, &q, &r)
}

#[pymodule]
fn rustlinalg(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(matmul, m)?)?;
    m.add_function(wrap_pyfunction!(cholesky, m)?)?;
    m.add_function(wrap_pyfunction!(solve_spd, m)?)?;
    m.add_function(wrap_pyfunction!(norm2, m)?)?;
    m.add_function(wrap_pyfunction!(qr, m)?)?;
    m.add_function(wrap_pyfunction!(eig_symmetric, m)?)?;
    m.add_function(wrap_pyfunction!(svd, m)?)?;
    m.add_function(wrap_pyfunction!(matrix_exp, m)?)?;
    m.add_function(wrap_pyfunction!(solve_lstsq, m)?)?;
    m.add_function(wrap_pyfunction!(real_schur, m)?)?;
    m.add_function(wrap_pyfunction!(solve_care, m)?)?;
    Ok(())
}