#!/usr/bin/env python3
"""Numpy-reference integration pipeline for cylinalg."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import numpy as np
from scipy.linalg import expm


FIXTURES = Path("/app/fixtures")


def _array64(value, ndim: int | None = None) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    if ndim is not None and arr.ndim != ndim:
        raise AssertionError(f"expected {ndim}D output, got shape {arr.shape}")
    return arr


def _load(name: str) -> np.ndarray:
    return np.load(FIXTURES / name)


def _pipeline_cases() -> list[dict[str, np.ndarray]]:
    a_svd = _load("A_svd_tall.npy")
    a_schur = _load("A_schur_general.npy")
    a_matlog = _load("A_matlog_spd.npy")
    a_sqrtm = _load("A_sqrtm_spd.npy")
    a_qz = _load("A_qz1.npy")
    b_qz = _load("B_qz1.npy")
    a_signm = _load("A_signm1.npy")
    a_syl = _load("A_syl1.npy")
    b_syl = _load("B_syl1.npy")
    c_syl = _load("C_syl1.npy")
    a_eig = _load("A_eig1.npy")

    return [
        {
            "svd": a_svd,
            "schur": a_schur,
            "matlog": a_matlog,
            "sqrtm": a_sqrtm,
            "qz_a": a_qz, "qz_b": b_qz,
            "signm": a_signm,
            "syl_a": a_syl, "syl_b": b_syl, "syl_c": c_syl,
            "eig": a_eig,
        },
        {
            "svd": _load("A_svd_wide.npy"),
            "schur": a_schur * 0.7 + 0.3 * np.eye(a_schur.shape[0]),
            "matlog": a_matlog + 0.5 * np.eye(a_matlog.shape[0]),
            "sqrtm": a_sqrtm + 0.5 * np.eye(a_sqrtm.shape[0]),
            "qz_a": a_qz * 1.2, "qz_b": b_qz + 0.1 * np.eye(b_qz.shape[0]),
            "signm": a_signm * 1.5,
            "syl_a": a_syl * 0.8, "syl_b": b_syl + np.eye(b_syl.shape[0]),
            "syl_c": c_syl * 0.7,
            "eig": a_eig * 0.5 + 0.5 * np.eye(a_eig.shape[0]),
        },
        {
            "svd": _load("A_svd_large.npy")[:18, :9],
            "schur": a_schur + 0.1 * np.eye(a_schur.shape[0]),
            "matlog": a_matlog * 1.2 + 0.3 * np.eye(a_matlog.shape[0]),
            "sqrtm": a_sqrtm * 0.8 + 0.2 * np.eye(a_sqrtm.shape[0]),
            "qz_a": _load("A_qz3.npy"), "qz_b": _load("B_qz3.npy"),
            "signm": _load("A_signm1.npy") + 0.1 * np.eye(6),
            "syl_a": _load("A_syl2.npy"), "syl_b": _load("B_syl2.npy"),
            "syl_c": _load("C_syl2.npy"),
            "eig": _load("A_eig_real.npy"),
        },
    ]


def run_pipeline(module_name: str = "cylinalg") -> list[dict[str, float]]:
    mod = importlib.import_module(module_name)
    results: list[dict[str, float]] = []

    for idx, case in enumerate(_pipeline_cases(), start=1):
        # --- SVD ---
        u, s, vt = mod.svd(case["svd"])
        u = _array64(u, 2)
        s = _array64(s, 1)
        vt = _array64(vt, 2)
        k = min(case["svd"].shape)
        svd_recon = float(np.max(np.abs(
            u[:, :k] @ np.diag(s) @ vt[:k, :] - case["svd"]
        )))

        # --- Schur ---
        T_schur, Q_schur = mod.schur(case["schur"])
        T_schur = _array64(T_schur, 2)
        Q_schur = _array64(Q_schur, 2)
        n_sch = case["schur"].shape[0]
        schur_recon = float(np.max(np.abs(
            Q_schur @ T_schur @ Q_schur.T - case["schur"]
        )))
        schur_Q_orth = float(np.max(np.abs(
            Q_schur.T @ Q_schur - np.eye(n_sch)
        )))

        # --- Matrix log ---
        log_out = _array64(mod.matrix_log(case["matlog"]), 2)
        log_roundtrip = expm(np.asarray(log_out, dtype=np.float64))
        matlog_roundtrip = float(np.max(np.abs(
            log_roundtrip - case["matlog"]
        )))

        # --- Matrix square root ---
        sqrt_out = _array64(mod.sqrtm(case["sqrtm"]), 2)
        sqrtm_squared = float(np.max(np.abs(
            sqrt_out @ sqrt_out - case["sqrtm"]
        )))

        # --- QZ ---
        S_qz, T_qz, Q_qz, Z_qz = mod.qz(case["qz_a"], case["qz_b"])
        S_qz = _array64(S_qz, 2)
        T_qz = _array64(T_qz, 2)
        Q_qz = _array64(Q_qz, 2)
        Z_qz = _array64(Z_qz, 2)
        n_qz = case["qz_a"].shape[0]
        qz_recon_a = float(np.max(np.abs(
            Q_qz.T @ case["qz_a"] @ Z_qz - S_qz
        )))
        qz_recon_b = float(np.max(np.abs(
            Q_qz.T @ case["qz_b"] @ Z_qz - T_qz
        )))
        qz_Q_orth = float(np.max(np.abs(
            Q_qz.T @ Q_qz - np.eye(n_qz)
        )))
        qz_Z_orth = float(np.max(np.abs(
            Z_qz.T @ Z_qz - np.eye(n_qz)
        )))

        # --- Sign ---
        sign_out = _array64(mod.signm(case["signm"]), 2)
        signm_sq = float(np.max(np.abs(
            sign_out @ sign_out - np.eye(case["signm"].shape[0])
        )))

        # --- Sylvester ---
        X_syl = _array64(mod.solve_sylvester(
            case["syl_a"], case["syl_b"], case["syl_c"]
        ), 2)
        syl_resid = float(np.max(np.abs(
            case["syl_a"] @ X_syl + X_syl @ case["syl_b"] - case["syl_c"]
        )))

        # --- Eig ---
        wr, wi, vecs = mod.eig(case["eig"])
        wr = _array64(wr, 1)
        wi = _array64(wi, 1)
        vecs = _array64(vecs, 2)
        A_eig = case["eig"]
        n_eig = A_eig.shape[0]

        # Reconstruct A @ v = lambda * v for each eigenvalue
        eig_max_resid = 0.0
        j = 0
        while j < n_eig:
            if abs(wi[j]) < 1e-14:
                # Real eigenvalue
                v = vecs[:, j]
                resid = np.abs(A_eig @ v - wr[j] * v).max()
                eig_max_resid = max(eig_max_resid, resid)
                j += 1
            else:
                # Complex conjugate pair
                vr = vecs[:, j]
                vi = vecs[:, j + 1]
                lam_r, lam_i = wr[j], wi[j]
                # A @ (vr + i*vi) = (lam_r + i*lam_i) * (vr + i*vi)
                # Real part: A@vr = lam_r*vr - lam_i*vi
                # Imag part: A@vi = lam_r*vi + lam_i*vr
                resid_r = np.abs(A_eig @ vr - (lam_r * vr - lam_i * vi)).max()
                resid_i = np.abs(A_eig @ vi - (lam_r * vi + lam_i * vr)).max()
                eig_max_resid = max(eig_max_resid, resid_r, resid_i)
                j += 2

        # --- Ordschur ---
        A_sch = case["schur"]
        n_sch2 = A_sch.shape[0]
        select_ord = [bool(i % 2 == 0) for i in range(n_sch2)]
        T_new, Q_new = mod.ordschur(T_schur, Q_schur, select_ord)
        T_new = _array64(T_new, 2)
        Q_new = _array64(Q_new, 2)
        ordschur_recon = float(np.max(np.abs(
            Q_new @ T_new @ Q_new.T - A_sch
        )))
        ordschur_Q_orth = float(np.max(np.abs(
            Q_new.T @ Q_new - np.eye(n_sch2)
        )))

        results.append({
            "case": float(idx),
            "svd_recon_max_abs": svd_recon,
            "schur_recon_max_abs": schur_recon,
            "schur_Q_orthogonality": schur_Q_orth,
            "matlog_roundtrip_max_abs": matlog_roundtrip,
            "sqrtm_squared_max_abs": sqrtm_squared,
            "qz_recon_A_max_abs": qz_recon_a,
            "qz_recon_B_max_abs": qz_recon_b,
            "qz_Q_orthogonality": qz_Q_orth,
            "qz_Z_orthogonality": qz_Z_orth,
            "signm_squared_max_abs": signm_sq,
            "sylvester_residual_max_abs": syl_resid,
            "eig_recon_max_abs": float(eig_max_resid),
            "ordschur_recon_max_abs": ordschur_recon,
            "ordschur_Q_orthogonality": ordschur_Q_orth,
        })

    return results


def main() -> int:
    payload = run_pipeline()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
