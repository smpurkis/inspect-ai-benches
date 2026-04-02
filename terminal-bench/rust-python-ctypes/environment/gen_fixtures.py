#!/usr/bin/env python3
"""Generate fixture .npy files for rustlinalg tests."""
import os
import numpy as np
from scipy.linalg import expm

os.makedirs("/app/fixtures", exist_ok=True)
rng = np.random.default_rng(20260218)

# --- Small fixtures ---

# matmul: 4x3 @ 3x5 -> 4x5
A_matmul = rng.standard_normal((4, 3)).astype(np.float64)
B_matmul = rng.standard_normal((3, 5)).astype(np.float64)
np.save("/app/fixtures/A_matmul.npy", A_matmul)
np.save("/app/fixtures/B_matmul.npy", B_matmul)

# Symmetric positive-definite: 6x6
X = rng.standard_normal((6, 6))
A_spd = (X @ X.T + 6.0 * np.eye(6)).astype(np.float64)
np.save("/app/fixtures/A_spd.npy", A_spd)

# Vector for solve_spd / norm2
b_vec = rng.standard_normal(6).astype(np.float64)
np.save("/app/fixtures/b_vec.npy", b_vec)

# --- Larger fixtures ---

# matmul: 50x30 @ 30x40
A_large = rng.standard_normal((50, 30)).astype(np.float64)
B_large = rng.standard_normal((30, 40)).astype(np.float64)
np.save("/app/fixtures/A_large.npy", A_large)
np.save("/app/fixtures/B_large.npy", B_large)

# SPD: 50x50
X_large = rng.standard_normal((50, 50))
A_spd_large = (X_large @ X_large.T + 50.0 * np.eye(50)).astype(np.float64)
b_large = rng.standard_normal(50).astype(np.float64)
np.save("/app/fixtures/A_spd_large.npy", A_spd_large)
np.save("/app/fixtures/b_large.npy", b_large)

# --- QR fixtures ---

# Tall matrix 8x5 (overdetermined)
A_qr = rng.standard_normal((8, 5)).astype(np.float64)
np.save("/app/fixtures/A_qr.npy", A_qr)

# Square matrix 6x6
A_qr_sq = rng.standard_normal((6, 6)).astype(np.float64)
np.save("/app/fixtures/A_qr_sq.npy", A_qr_sq)

# Large QR: 40x25
A_qr_large = rng.standard_normal((40, 25)).astype(np.float64)
np.save("/app/fixtures/A_qr_large.npy", A_qr_large)

# --- Symmetric eigenvalue fixtures ---

# Symmetric matrix with known clustered eigenvalues (hard case)
D_clustered = np.diag([1.0, 1.0001, 1.0002, 5.0, 5.0001, 10.0])
Q_rand, _ = np.linalg.qr(rng.standard_normal((6, 6)))
A_sym_clustered = (Q_rand @ D_clustered @ Q_rand.T).astype(np.float64)
A_sym_clustered = 0.5 * (A_sym_clustered + A_sym_clustered.T)
np.save("/app/fixtures/A_sym_clustered.npy", A_sym_clustered)

# Larger symmetric 30x30
X_sym30 = rng.standard_normal((30, 30))
A_sym_large = (X_sym30 + X_sym30.T).astype(np.float64) * 0.5
np.save("/app/fixtures/A_sym_large.npy", A_sym_large)

# --- SVD fixtures ---

# Tall non-square 7x4
A_svd_tall = rng.standard_normal((7, 4)).astype(np.float64)
np.save("/app/fixtures/A_svd_tall.npy", A_svd_tall)

# Wide non-square 4x7
A_svd_wide = rng.standard_normal((4, 7)).astype(np.float64)
np.save("/app/fixtures/A_svd_wide.npy", A_svd_wide)

# Rank-deficient 6x6 (rank 3)
U_rd = rng.standard_normal((6, 3))
V_rd = rng.standard_normal((3, 6))
A_svd_rankdef = (U_rd @ V_rd).astype(np.float64)
np.save("/app/fixtures/A_svd_rankdef.npy", A_svd_rankdef)

# Large SVD: 25x15
A_svd_large = rng.standard_normal((25, 15)).astype(np.float64)
np.save("/app/fixtures/A_svd_large.npy", A_svd_large)

# --- Matrix exponential fixtures ---

# Small general 4x4
A_exp_small = rng.standard_normal((4, 4)).astype(np.float64)
np.save("/app/fixtures/A_exp_small.npy", A_exp_small)
np.save("/app/fixtures/A_exp_small_ref.npy", expm(A_exp_small))

# Nilpotent 4x4 (strictly upper triangular - exact exponential is finite sum)
A_nilpotent = np.zeros((4, 4), dtype=np.float64)
A_nilpotent[0, 1] = 2.0
A_nilpotent[0, 2] = 3.0
A_nilpotent[1, 3] = -1.0
A_nilpotent[0, 3] = 4.0
A_nilpotent[1, 2] = 0.5
A_nilpotent[2, 3] = 1.5
np.save("/app/fixtures/A_nilpotent.npy", A_nilpotent)
np.save("/app/fixtures/A_nilpotent_ref.npy", expm(A_nilpotent))

# Skew-symmetric 5x5 (exp should be orthogonal)
X_skew = rng.standard_normal((5, 5))
A_skew = (X_skew - X_skew.T).astype(np.float64) * 0.5
np.save("/app/fixtures/A_skew.npy", A_skew)
np.save("/app/fixtures/A_skew_ref.npy", expm(A_skew))

# Large norm matrix 5x5 (tests scaling-and-squaring)
A_exp_large_norm = (rng.standard_normal((5, 5)) * 20.0).astype(np.float64)
np.save("/app/fixtures/A_exp_large_norm.npy", A_exp_large_norm)
np.save("/app/fixtures/A_exp_large_norm_ref.npy", expm(A_exp_large_norm))

# --- Least-squares fixtures ---

# Overdetermined 8x4
A_lstsq = rng.standard_normal((8, 4)).astype(np.float64)
b_lstsq = rng.standard_normal(8).astype(np.float64)
np.save("/app/fixtures/A_lstsq.npy", A_lstsq)
np.save("/app/fixtures/b_lstsq.npy", b_lstsq)

# Large overdetermined 50x10
A_lstsq_large = rng.standard_normal((50, 10)).astype(np.float64)
b_lstsq_large = rng.standard_normal(50).astype(np.float64)
np.save("/app/fixtures/A_lstsq_large.npy", A_lstsq_large)
np.save("/app/fixtures/b_lstsq_large.npy", b_lstsq_large)

# Exactly determined (square) 5x5
A_lstsq_sq = rng.standard_normal((5, 5)).astype(np.float64)
b_lstsq_sq = rng.standard_normal(5).astype(np.float64)
np.save("/app/fixtures/A_lstsq_sq.npy", A_lstsq_sq)
np.save("/app/fixtures/b_lstsq_sq.npy", b_lstsq_sq)

print("Fixtures generated successfully")
