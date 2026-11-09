use crate::matrix::Matrix;

pub(crate) fn hessenberg(mut a: Matrix) -> (Matrix, Matrix) {
    let n = a.n();
    let mut q = Matrix::identity(n);
    for k in 0..n.saturating_sub(2) {
        let m = n - k - 1;
        let mut v: Vec<f64> = (0..m).map(|i| a[(k + 1 + i, k)]).collect();
        let norm = v.iter().fold(0.0_f64, |r, &x| r.hypot(x));
        if norm == 0.0 { continue; }
        v[0] += if v[0] >= 0.0 { norm } else { -norm };
        let vv: f64 = v.iter().map(|x| x * x).sum();
        if vv == 0.0 { continue; }
        let beta = 2.0 / vv;
        for j in k..n {
            let dot = beta * (0..m).map(|i| v[i] * a[(k + 1 + i, j)]).sum::<f64>();
            for i in 0..m { a[(k + 1 + i, j)] -= dot * v[i]; }
        }
        for i in 0..n {
            let dot = beta * (0..m).map(|j| a[(i, k + 1 + j)] * v[j]).sum::<f64>();
            for j in 0..m { a[(i, k + 1 + j)] -= dot * v[j]; }
        }
        for i in 0..n {
            let dot = beta * (0..m).map(|j| q[(i, k + 1 + j)] * v[j]).sum::<f64>();
            for j in 0..m { q[(i, k + 1 + j)] -= dot * v[j]; }
        }
        for i in k + 2..n { a[(i, k)] = 0.0; }
    }
    (a, q)
}
