#!/usr/bin/env python3
"""Numpy-reference integration pipeline for rustlinalg."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import numpy as np


FIXTURES = Path("/app/fixtures")


def _array64(value, ndim: int | None = None) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    if ndim is not None and arr.ndim != ndim:
        raise AssertionError(f"expected {ndim}D output, got shape {arr.shape}")
    return arr


def _load(name: str) -> np.ndarray:
    return np.load(FIXTURES / name)


def _pipeline_cases() -> list[dict[str, np.ndarray]]:
    a_small = _load("A_matmul.npy")
    b_small = _load("B_matmul.npy")
    a_spd = _load("A_spd.npy")
    b_vec = _load("b_vec.npy")
    a_qr = _load("A_qr.npy")
    a_svd = _load("A_svd_tall.npy")
    a_exp = _load("A_exp_small.npy")
    a_lstsq = _load("A_lstsq.npy")
    b_lstsq = _load("b_lstsq.npy")

    return [
        {
            "mat_a": a_small,
            "mat_b": b_small,
            "spd": a_spd,
            "vec": b_vec,
            "qr": a_qr,
            "svd": a_svd,
            "exp": a_exp,
            "lstsq_a": a_lstsq,
            "lstsq_b": b_lstsq,
        },
        {
            "mat_a": a_small * 0.75,
            "mat_b": b_small * 1.2,
            "spd": a_spd + 0.35 * np.eye(a_spd.shape[0]),
            "vec": b_vec * 1.5,
            "qr": a_qr * 0.3,
            "svd": _load("A_svd_wide.npy"),
            "exp": a_exp * 0.2,
            "lstsq_a": a_lstsq + 0.1,
            "lstsq_b": b_lstsq - 0.05,
        },
        {
            "mat_a": _load("A_large.npy")[:20, :15],
            "mat_b": _load("B_large.npy")[:15, :18],
            "spd": _load("A_spd_large.npy")[:12, :12] + 0.2 * np.eye(12),
            "vec": _load("b_large.npy")[:12],
            "qr": _load("A_qr_large.npy")[:18, :10],
            "svd": _load("A_svd_large.npy")[:18, :9],
            "exp": _load("A_exp_small.npy") * 0.05,
            "lstsq_a": _load("A_lstsq_large.npy")[:24, :7],
            "lstsq_b": _load("b_lstsq_large.npy")[:24],
        },
    ]


def run_pipeline(module_name: str = "rustlinalg") -> list[dict[str, float]]:
    rust = importlib.import_module(module_name)
    results: list[dict[str, float]] = []

    for idx, case in enumerate(_pipeline_cases(), start=1):
        mm = _array64(rust.matmul(case["mat_a"], case["mat_b"]), 2)
        mm_ref = case["mat_a"] @ case["mat_b"]

        chol = _array64(rust.cholesky(case["spd"]), 2)
        chol_ref = np.linalg.cholesky(case["spd"])

        x = _array64(rust.solve_spd(case["spd"], case["vec"]), 1)
        x_ref = np.linalg.solve(case["spd"], case["vec"])

        n2 = float(rust.norm2(x))
        n2_ref = float(np.linalg.norm(x_ref))

        q, r = rust.qr(case["qr"])
        q = _array64(q, 2)
        r = _array64(r, 2)
        q_ref, r_ref = np.linalg.qr(case["qr"], mode="complete")

        evals, evecs = rust.eig_symmetric(case["spd"])
        evals = _array64(evals, 1)
        evecs = _array64(evecs, 2)
        evals_ref, evecs_ref = np.linalg.eigh(case["spd"])

        u, s, vt = rust.svd(case["svd"])
        u = _array64(u, 2)
        s = _array64(s, 1)
        vt = _array64(vt, 2)
        u_ref, s_ref, vt_ref = np.linalg.svd(case["svd"], full_matrices=True)

        exp_out = _array64(rust.matrix_exp(case["exp"]), 2)
        exp_ref = _load("A_exp_small_ref.npy") if idx == 1 else None
        if exp_ref is None:
            vals, vecs = np.linalg.eig(case["exp"])
            exp_ref = np.real_if_close(
                vecs @ np.diag(np.exp(vals)) @ np.linalg.inv(vecs)
            )

        x_lstsq = _array64(rust.solve_lstsq(case["lstsq_a"], case["lstsq_b"]), 1)
        x_lstsq_ref, _, _, _ = np.linalg.lstsq(
            case["lstsq_a"], case["lstsq_b"], rcond=None
        )

        results.append(
            {
                "case": float(idx),
                "matmul_max_abs": float(np.max(np.abs(mm - mm_ref))),
                "cholesky_recon_max_abs": float(
                    np.max(np.abs(chol @ chol.T - case["spd"]))
                ),
                "cholesky_ref_max_abs": float(np.max(np.abs(chol - chol_ref))),
                "solve_spd_max_abs": float(np.max(np.abs(x - x_ref))),
                "norm2_abs": float(abs(n2 - n2_ref)),
                "qr_recon_max_abs": float(np.max(np.abs(q @ r - case["qr"]))),
                "qr_ref_recon_max_abs": float(
                    np.max(np.abs(q_ref @ r_ref - case["qr"]))
                ),
                "eig_vals_max_abs": float(np.max(np.abs(evals - evals_ref))),
                "eig_recon_max_abs": float(
                    np.max(np.abs(evecs @ np.diag(evals) @ evecs.T - case["spd"]))
                ),
                "eig_ref_recon_max_abs": float(
                    np.max(
                        np.abs(
                            evecs_ref @ np.diag(evals_ref) @ evecs_ref.T - case["spd"]
                        )
                    )
                ),
                "svd_vals_max_abs": float(np.max(np.abs(s - s_ref))),
                "svd_recon_max_abs": float(
                    np.max(
                        np.abs(
                            u[:, : s.shape[0]] @ np.diag(s) @ vt[: s.shape[0], :]
                            - case["svd"]
                        )
                    )
                ),
                "svd_ref_recon_max_abs": float(
                    np.max(
                        np.abs(
                            u_ref[:, : s_ref.shape[0]]
                            @ np.diag(s_ref)
                            @ vt_ref[: s_ref.shape[0], :]
                            - case["svd"]
                        )
                    )
                ),
                "matrix_exp_max_abs": float(np.max(np.abs(exp_out - exp_ref))),
                "lstsq_max_abs": float(np.max(np.abs(x_lstsq - x_lstsq_ref))),
            }
        )

    return results


def main() -> int:
    payload = run_pipeline()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
