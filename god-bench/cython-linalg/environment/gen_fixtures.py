#!/usr/bin/env python3
"""Generate fixture .npy files for cylinalg tests."""
import os
import numpy as np
from scipy.linalg import (
    expm, schur as scipy_schur, logm as scipy_logm, sqrtm as scipy_sqrtm,
    qz as scipy_qz, solve_sylvester as scipy_solve_sylvester,
    ordqz as scipy_ordqz, polar as scipy_polar,
)

os.makedirs("/app/fixtures", exist_ok=True)
rng = np.random.default_rng(20260218)

# ===================================================================
# SVD fixtures
# ===================================================================

# Tall matrix 7x4
A_svd_tall = rng.standard_normal((7, 4)).astype(np.float64)
np.save("/app/fixtures/A_svd_tall.npy", A_svd_tall)

# Wide matrix 4x7
A_svd_wide = rng.standard_normal((4, 7)).astype(np.float64)
np.save("/app/fixtures/A_svd_wide.npy", A_svd_wide)

# Rank-deficient 6x6 (rank 3)
U_rd = rng.standard_normal((6, 3))
V_rd = rng.standard_normal((3, 6))
A_svd_rankdef = (U_rd @ V_rd).astype(np.float64)
np.save("/app/fixtures/A_svd_rankdef.npy", A_svd_rankdef)

# Large SVD 25x15
A_svd_large = rng.standard_normal((25, 15)).astype(np.float64)
np.save("/app/fixtures/A_svd_large.npy", A_svd_large)

# ===================================================================
# Schur decomposition fixtures
# ===================================================================

# 6x6 general (non-symmetric)
A_schur_general = rng.standard_normal((6, 6)).astype(np.float64)
np.save("/app/fixtures/A_schur_general.npy", A_schur_general)
T_schur_ref, Q_schur_ref = scipy_schur(A_schur_general, output='real')
np.save("/app/fixtures/T_schur_general_ref.npy", T_schur_ref)
np.save("/app/fixtures/Q_schur_general_ref.npy", Q_schur_ref)

# Matrix with complex eigenvalue pairs
A_schur_complex = np.array([
    [ 0.5,  1.2, -0.3,  0.7,  0.1, -0.4],
    [-1.2,  0.5,  0.4, -0.1,  0.8,  0.2],
    [ 0.3, -0.4,  1.5,  2.1,  0.6, -0.3],
    [-0.7,  0.1, -2.1,  1.5,  0.2,  0.5],
    [ 0.1, -0.8, -0.6, -0.2,  0.8,  1.7],
    [ 0.4, -0.2,  0.3, -0.5, -1.7,  0.8],
], dtype=np.float64)
np.save("/app/fixtures/A_schur_complex.npy", A_schur_complex)

# ===================================================================
# Matrix logarithm fixtures
# ===================================================================

# SPD matrix (guaranteed positive eigenvalues)
X_ml = rng.standard_normal((6, 6))
A_matlog_spd = (X_ml @ X_ml.T + 4.0 * np.eye(6)).astype(np.float64)
np.save("/app/fixtures/A_matlog_spd.npy", A_matlog_spd)
np.save("/app/fixtures/A_matlog_spd_ref.npy", scipy_logm(A_matlog_spd))

# Matrix with complex eigenvalues (no negative real eigenvalues)
B_ml = np.array([
    [ 3.0,  1.5, -0.5,  0.3],
    [-1.5,  3.0,  0.8, -0.2],
    [ 0.5, -0.8,  4.0,  1.2],
    [-0.3,  0.2, -1.2,  4.0],
], dtype=np.float64)
np.save("/app/fixtures/A_matlog_complex.npy", B_ml)
np.save("/app/fixtures/A_matlog_complex_ref.npy", scipy_logm(B_ml))

# ===================================================================
# Matrix square root fixtures
# ===================================================================

# SPD matrix for sqrtm (positive eigenvalues -> unique real square root)
X_sq = rng.standard_normal((6, 6))
A_sqrtm_spd = (X_sq @ X_sq.T + 5.0 * np.eye(6)).astype(np.float64)
np.save("/app/fixtures/A_sqrtm_spd.npy", A_sqrtm_spd)
np.save("/app/fixtures/A_sqrtm_spd_ref.npy", scipy_sqrtm(A_sqrtm_spd))

# Matrix with complex eigenvalues (no negative real eigenvalues)
A_sqrtm_complex = np.array([
    [ 2.5,  1.8, -0.4,  0.6],
    [-1.8,  2.5,  0.7, -0.3],
    [ 0.4, -0.7,  3.5,  1.4],
    [-0.6,  0.3, -1.4,  3.5],
], dtype=np.float64)
np.save("/app/fixtures/A_sqrtm_complex.npy", A_sqrtm_complex)
np.save("/app/fixtures/A_sqrtm_complex_ref.npy", scipy_sqrtm(A_sqrtm_complex))

# Large SPD for sqrtm stress test
X_sq_large = rng.standard_normal((20, 20))
A_sqrtm_large = (X_sq_large @ X_sq_large.T + 10.0 * np.eye(20)).astype(np.float64)
np.save("/app/fixtures/A_sqrtm_large.npy", A_sqrtm_large)
np.save("/app/fixtures/A_sqrtm_large_ref.npy", scipy_sqrtm(A_sqrtm_large))

# ===================================================================
# QZ (Generalized Schur) decomposition fixtures
# ===================================================================

# Basic pair: 5x5 general matrices
A_qz1 = rng.standard_normal((5, 5)).astype(np.float64)
B_qz1 = rng.standard_normal((5, 5)).astype(np.float64)
np.save("/app/fixtures/A_qz1.npy", A_qz1)
np.save("/app/fixtures/B_qz1.npy", B_qz1)
AA1, BB1, Q1, Z1 = scipy_qz(A_qz1, B_qz1, output='real')
np.save("/app/fixtures/AA_qz1_ref.npy", AA1)
np.save("/app/fixtures/BB_qz1_ref.npy", BB1)

# Pair with near-singular B (tests infinite eigenvalue handling)
A_qz2 = rng.standard_normal((5, 5)).astype(np.float64)
B_qz2 = rng.standard_normal((5, 5)).astype(np.float64)
B_qz2[3, :] *= 1e-14  # Make nearly singular
np.save("/app/fixtures/A_qz2.npy", A_qz2)
np.save("/app/fixtures/B_qz2.npy", B_qz2)

# Larger pair: 8x8
A_qz3 = rng.standard_normal((8, 8)).astype(np.float64)
B_qz3 = rng.standard_normal((8, 8)).astype(np.float64)
np.save("/app/fixtures/A_qz3.npy", A_qz3)
np.save("/app/fixtures/B_qz3.npy", B_qz3)

# Large stress pair: 20x20
A_qz_large = rng.standard_normal((20, 20)).astype(np.float64)
B_qz_large = rng.standard_normal((20, 20)).astype(np.float64)
np.save("/app/fixtures/A_qz_large.npy", A_qz_large)
np.save("/app/fixtures/B_qz_large.npy", B_qz_large)

# ===================================================================
# Matrix sign function fixtures
# ===================================================================

# Matrix with eigenvalues in both half-planes (general case)
A_signm1 = rng.standard_normal((6, 6)).astype(np.float64)
np.save("/app/fixtures/A_signm1.npy", A_signm1)

# Matrix with all-real eigenvalues in both half-planes
eigs_real = np.array([-3.0, -1.5, -0.5, 0.5, 1.5, 3.0])
Q_sr, _ = np.linalg.qr(rng.standard_normal((6, 6)))
A_signm_real = (Q_sr @ np.diag(eigs_real) @ Q_sr.T).astype(np.float64)
np.save("/app/fixtures/A_signm_real.npy", A_signm_real)

# Matrix with complex eigenvalues in both half-planes
A_signm_complex = np.array([
    [ 1.0,  2.0, -0.5,  0.3],
    [-2.0,  1.0,  0.4, -0.2],
    [ 0.5, -0.4, -1.5,  1.8],
    [-0.3,  0.2, -1.8, -1.5],
], dtype=np.float64)
np.save("/app/fixtures/A_signm_complex.npy", A_signm_complex)

# Large stress test
A_signm_large = rng.standard_normal((15, 15)).astype(np.float64)
np.save("/app/fixtures/A_signm_large.npy", A_signm_large)

# ===================================================================
# Sylvester equation fixtures: AX + XB = C
# ===================================================================

# Basic 5x5 case: A, B have well-separated spectra
A_syl1 = rng.standard_normal((5, 5)).astype(np.float64)
B_syl1 = rng.standard_normal((5, 5)).astype(np.float64) + 5.0 * np.eye(5)  # shift to separate spectra
C_syl1 = rng.standard_normal((5, 5)).astype(np.float64)
X_syl1_ref = scipy_solve_sylvester(A_syl1, B_syl1, C_syl1)
np.save("/app/fixtures/A_syl1.npy", A_syl1)
np.save("/app/fixtures/B_syl1.npy", B_syl1)
np.save("/app/fixtures/C_syl1.npy", C_syl1)
np.save("/app/fixtures/X_syl1_ref.npy", X_syl1_ref)

# Rectangular: A is 4x4, B is 6x6, C is 4x6
A_syl2 = rng.standard_normal((4, 4)).astype(np.float64)
B_syl2 = rng.standard_normal((6, 6)).astype(np.float64) + 4.0 * np.eye(6)
C_syl2 = rng.standard_normal((4, 6)).astype(np.float64)
X_syl2_ref = scipy_solve_sylvester(A_syl2, B_syl2, C_syl2)
np.save("/app/fixtures/A_syl2.npy", A_syl2)
np.save("/app/fixtures/B_syl2.npy", B_syl2)
np.save("/app/fixtures/C_syl2.npy", C_syl2)
np.save("/app/fixtures/X_syl2_ref.npy", X_syl2_ref)

# Large 15x15 case
A_syl3 = rng.standard_normal((15, 15)).astype(np.float64)
B_syl3 = rng.standard_normal((15, 15)).astype(np.float64) + 8.0 * np.eye(15)
C_syl3 = rng.standard_normal((15, 15)).astype(np.float64)
X_syl3_ref = scipy_solve_sylvester(A_syl3, B_syl3, C_syl3)
np.save("/app/fixtures/A_syl3.npy", A_syl3)
np.save("/app/fixtures/B_syl3.npy", B_syl3)
np.save("/app/fixtures/C_syl3.npy", C_syl3)
np.save("/app/fixtures/X_syl3_ref.npy", X_syl3_ref)

# ===================================================================
# Nonsymmetric eigenvalue problem fixtures
# ===================================================================

# General 6x6 with mix of real and complex eigenvalues
A_eig1 = np.array([
    [ 0.5,  1.2, -0.3,  0.7,  0.1, -0.4],
    [-1.2,  0.5,  0.4, -0.1,  0.8,  0.2],
    [ 0.3, -0.4,  2.0,  0.0,  0.6, -0.3],
    [-0.7,  0.1,  0.0,  3.0,  0.2,  0.5],
    [ 0.1, -0.8, -0.6, -0.2,  0.8,  1.7],
    [ 0.4, -0.2,  0.3, -0.5, -1.7,  0.8],
], dtype=np.float64)
np.save("/app/fixtures/A_eig1.npy", A_eig1)

# Matrix with all real eigenvalues (symmetric-ish, diagonally dominant)
X_eig_real = rng.standard_normal((6, 6))
A_eig_real = (X_eig_real + X_eig_real.T).astype(np.float64) * 0.5
np.save("/app/fixtures/A_eig_real.npy", A_eig_real)

# Near-defective matrix (clustered eigenvalues)
Q_nd, _ = np.linalg.qr(rng.standard_normal((8, 8)))
eigs_nd = np.array([1.0, 1.0 + 1e-8, 1.0 + 2e-8, 5.0, -2.0, 3.0, -1.0, 4.0])
A_eig_neardef = (Q_nd @ np.diag(eigs_nd) @ Q_nd.T).astype(np.float64)
np.save("/app/fixtures/A_eig_neardef.npy", A_eig_neardef)

# Large 15x15 general matrix
A_eig_large = rng.standard_normal((15, 15)).astype(np.float64)
np.save("/app/fixtures/A_eig_large.npy", A_eig_large)

# ===================================================================
# Pipeline fixtures (supplementary)
# ===================================================================

# SPD matrix used across multiple pipeline functions
X_spd = rng.standard_normal((6, 6))
A_spd = (X_spd @ X_spd.T + 6.0 * np.eye(6)).astype(np.float64)
np.save("/app/fixtures/A_spd.npy", A_spd)

# ===================================================================
# Ordered Schur decomposition fixtures
# ===================================================================

# 6x6 matrix with mix of real/complex eigenvalues for reordering
A_ordschur = np.array([
    [ 0.5,  1.2, -0.3,  0.7,  0.1, -0.4],
    [-1.2,  0.5,  0.4, -0.1,  0.8,  0.2],
    [ 0.3, -0.4,  2.0,  0.0,  0.6, -0.3],
    [-0.7,  0.1,  0.0,  3.0,  0.2,  0.5],
    [ 0.1, -0.8, -0.6, -0.2,  0.8,  1.7],
    [ 0.4, -0.2,  0.3, -0.5, -1.7,  0.8],
], dtype=np.float64)
T_ord, Q_ord = scipy_schur(A_ordschur, output='real')
np.save("/app/fixtures/A_ordschur1.npy", A_ordschur)
np.save("/app/fixtures/T_ordschur1.npy", T_ord)
np.save("/app/fixtures/Q_ordschur1.npy", Q_ord)
# Select: eigenvalues with real part > 1.0
eigs_ord = np.linalg.eigvals(A_ordschur)
select_ord1 = [bool(e.real > 1.0) for e in sorted(eigs_ord, key=lambda x: x.real)]
np.save("/app/fixtures/select_ordschur1.npy", np.array(select_ord1))

# 8x8 general for stress test
A_ordschur2 = rng.standard_normal((8, 8)).astype(np.float64)
T_ord2, Q_ord2 = scipy_schur(A_ordschur2, output='real')
np.save("/app/fixtures/A_ordschur2.npy", A_ordschur2)
np.save("/app/fixtures/T_ordschur2.npy", T_ord2)
np.save("/app/fixtures/Q_ordschur2.npy", Q_ord2)
eigs_ord2 = np.linalg.eigvals(A_ordschur2)
select_ord2 = [bool(e.real > 0.0) for e in sorted(eigs_ord2, key=lambda x: x.real)]
np.save("/app/fixtures/select_ordschur2.npy", np.array(select_ord2))

# 15x15 large stress
A_ordschur3 = rng.standard_normal((15, 15)).astype(np.float64)
T_ord3, Q_ord3 = scipy_schur(A_ordschur3, output='real')
np.save("/app/fixtures/A_ordschur3.npy", A_ordschur3)
np.save("/app/fixtures/T_ordschur3.npy", T_ord3)
np.save("/app/fixtures/Q_ordschur3.npy", Q_ord3)

# ===================================================================
# Matrix exponential fixtures
# ===================================================================

# Small 4x4 general matrix
A_expm_small = rng.standard_normal((4, 4)).astype(np.float64)
np.save("/app/fixtures/A_expm_small.npy", A_expm_small)
np.save("/app/fixtures/A_expm_small_ref.npy", expm(A_expm_small))

# Nilpotent (strictly upper triangular)
A_expm_nilp = np.zeros((4, 4), dtype=np.float64)
A_expm_nilp[0, 1] = 2.0; A_expm_nilp[0, 2] = 3.0; A_expm_nilp[0, 3] = 4.0
A_expm_nilp[1, 2] = 0.5; A_expm_nilp[1, 3] = -1.0
A_expm_nilp[2, 3] = 1.5
np.save("/app/fixtures/A_expm_nilpotent.npy", A_expm_nilp)
np.save("/app/fixtures/A_expm_nilpotent_ref.npy", expm(A_expm_nilp))

# Skew-symmetric (exp should be orthogonal)
X_skew = rng.standard_normal((5, 5))
A_expm_skew = (X_skew - X_skew.T).astype(np.float64) * 0.5
np.save("/app/fixtures/A_expm_skew.npy", A_expm_skew)
np.save("/app/fixtures/A_expm_skew_ref.npy", expm(A_expm_skew))

# Large-norm matrix (tests scaling+squaring)
A_expm_large = (rng.standard_normal((6, 6)) * 20.0).astype(np.float64)
np.save("/app/fixtures/A_expm_large.npy", A_expm_large)
np.save("/app/fixtures/A_expm_large_ref.npy", expm(A_expm_large))

# Diagonal matrix (trivial but tests correctness)
A_expm_diag = np.diag(rng.standard_normal(5)).astype(np.float64)
np.save("/app/fixtures/A_expm_diag.npy", A_expm_diag)
np.save("/app/fixtures/A_expm_diag_ref.npy", expm(A_expm_diag))

# 10x10 stress test
A_expm_stress = rng.standard_normal((10, 10)).astype(np.float64) * 3.0
np.save("/app/fixtures/A_expm_stress.npy", A_expm_stress)
np.save("/app/fixtures/A_expm_stress_ref.npy", expm(A_expm_stress))

# ===================================================================
# Polar decomposition fixtures
# ===================================================================

# Square 6x6 general matrix
A_polar1 = rng.standard_normal((6, 6)).astype(np.float64)
U_polar1, H_polar1 = scipy_polar(A_polar1)
np.save("/app/fixtures/A_polar1.npy", A_polar1)
np.save("/app/fixtures/U_polar1_ref.npy", U_polar1)
np.save("/app/fixtures/H_polar1_ref.npy", H_polar1)

# Tall matrix 8x5 (m > n)
A_polar_tall = rng.standard_normal((8, 5)).astype(np.float64)
U_polar_tall, H_polar_tall = scipy_polar(A_polar_tall)
np.save("/app/fixtures/A_polar_tall.npy", A_polar_tall)
np.save("/app/fixtures/U_polar_tall_ref.npy", U_polar_tall)
np.save("/app/fixtures/H_polar_tall_ref.npy", H_polar_tall)

# Nearly singular (rank-deficient)
U_rd2 = rng.standard_normal((6, 3))
V_rd2 = rng.standard_normal((3, 6))
A_polar_rankdef = (U_rd2 @ V_rd2).astype(np.float64)
U_polar_rd, H_polar_rd = scipy_polar(A_polar_rankdef)
np.save("/app/fixtures/A_polar_rankdef.npy", A_polar_rankdef)
np.save("/app/fixtures/U_polar_rankdef_ref.npy", U_polar_rd)
np.save("/app/fixtures/H_polar_rankdef_ref.npy", H_polar_rd)

# Large 15x15 stress
A_polar_large = rng.standard_normal((15, 15)).astype(np.float64)
U_polar_large, H_polar_large = scipy_polar(A_polar_large)
np.save("/app/fixtures/A_polar_large.npy", A_polar_large)
np.save("/app/fixtures/U_polar_large_ref.npy", U_polar_large)
np.save("/app/fixtures/H_polar_large_ref.npy", H_polar_large)

print("Fixtures generated successfully")
