#!/usr/bin/env python3

import hashlib
import subprocess
import tempfile
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent
FILES = BASE

PUBLIC_TEST = FILES / "cifar_public_test.npz"

CARGO_PROJECT = BASE / "cifar-infer"
CARGO_TOML = CARGO_PROJECT / "Cargo.toml"
PUBLIC_PREDS = BASE / "burn_public_test_preds.npy"

PUBLIC_SHA256 = "f3548cb190158b2e09db31d86e9f2e670778c9b19c53d793d7778ecee20d595b"

MIN_PUBLIC_ACC = 0.60


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_preds(path: Path, expected_len: int) -> np.ndarray:
    if not path.exists():
        raise AssertionError(f"Missing predictions file: {path}")
    arr = np.load(path)
    if arr.shape != (expected_len,):
        raise AssertionError(
            f"{path.name} shape mismatch: got {arr.shape}, expected {(expected_len,)}"
        )
    if not np.issubdtype(arr.dtype, np.integer):
        raise AssertionError(f"{path.name} dtype must be integer")
    if int(arr.min()) < 0 or int(arr.max()) > 9:
        raise AssertionError(f"{path.name} has class IDs outside [0, 9]")
    return arr.astype(np.int64)


def run_infer(input_npz: Path, output_npy: Path) -> None:
    """Run inference via cargo run --release."""
    cmd = [
        "cargo",
        "run",
        "--release",
        "--manifest-path",
        str(CARGO_TOML),
        "--",
        "--input-npz",
        str(input_npz),
        "--output-npy",
        str(output_npy),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise AssertionError(
            "Inference via cargo run failed. "
            f"cmd={' '.join(cmd)}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )


def test_burn_model_record_exists() -> None:
    """The cifar-infer project must contain at least one model record file (not a stub)."""
    if not CARGO_PROJECT.exists():
        raise AssertionError(f"Missing cifar-infer project at {CARGO_PROJECT}")
    model_files = []
    for ext in ("*.mpk", "*.bin", "*.json.gz", "*.pt", "*.mpk.gz"):
        model_files.extend(CARGO_PROJECT.rglob(ext))
    assert len(model_files) > 0, (
        "No model record files found in cifar-infer/ "
        "(expected *.mpk, *.bin, *.json.gz, *.pt, or *.mpk.gz)"
    )
    largest = max(f.stat().st_size for f in model_files)
    assert largest > 1000, (
        f"Largest model record file is only {largest} bytes — too small to contain a real model"
    )


def test_cargo_project_present() -> None:
    """Verify the Cargo project exists and depends on burn."""
    if not CARGO_TOML.exists():
        raise AssertionError(f"Missing Cargo.toml at {CARGO_TOML}")

    cargo_text = CARGO_TOML.read_text(encoding="utf-8")
    cargo_lower = cargo_text.lower()
    if "burn" not in cargo_lower:
        raise AssertionError("Cargo.toml must declare 'burn' as a dependency")


def test_public_accuracy_target() -> None:
    labels = np.load(PUBLIC_TEST)["test_labels"].astype(np.int64)
    preds = load_preds(PUBLIC_PREDS, labels.shape[0])
    acc = float((preds == labels).mean())

    assert acc >= MIN_PUBLIC_ACC, (
        f"public accuracy {acc:.4f} is below {MIN_PUBLIC_ACC:.2f}"
    )


def test_inference_command_reproduces_public_preds() -> None:
    """Run cargo run --release and verify output matches saved predictions."""
    labels = np.load(PUBLIC_TEST)["test_labels"].astype(np.int64)
    expected = load_preds(PUBLIC_PREDS, labels.shape[0])

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "public_preds.npy"
        run_infer(PUBLIC_TEST, out_path)
        inferred = load_preds(out_path, labels.shape[0])

    if not np.array_equal(inferred, expected):
        raise AssertionError(
            "cargo run inference output on public test must match burn_public_test_preds.npy"
        )


def test_cargo_builds_release() -> None:
    """Verify that the Cargo project compiles in release mode without errors."""
    cmd = [
        "cargo",
        "build",
        "--release",
        "--manifest-path",
        str(CARGO_TOML),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, (
        f"cargo build --release failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
