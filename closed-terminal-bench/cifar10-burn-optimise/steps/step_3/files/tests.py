#!/usr/bin/env python3

import hashlib
import subprocess
import tempfile
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent
STEP1_FILES = BASE.parent.parent / "step_1" / "files"

PUBLIC_TEST = STEP1_FILES / "cifar_public_test.npz"

CARGO_PROJECT = BASE / "cifar-infer"
CARGO_TOML = CARGO_PROJECT / "Cargo.toml"
OPT_PUBLIC_PREDS = BASE / "optimized_public_test_preds.npy"

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
            "Step 3 inference via cargo run failed. "
            f"cmd={' '.join(cmd)}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )


def test_step3_accuracy_improvement_over_step2() -> None:
    """Step 3 optimized model must outperform step 2 baseline on public test set."""
    STEP2_CARGO_TOML = BASE.parent.parent / "step_2" / "files" / "cifar-infer" / "Cargo.toml"
    if not STEP2_CARGO_TOML.exists():
        raise AssertionError(f"Missing step 2 Cargo.toml at {STEP2_CARGO_TOML}")

    labels = np.load(PUBLIC_TEST)["test_labels"].astype(np.int64)
    n = labels.shape[0]

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        # Run step 2 inference
        step2_out = tmp / "step2_preds.npy"
        step2_cmd = [
            "cargo", "run", "--release",
            "--manifest-path", str(STEP2_CARGO_TOML),
            "--", "--input-npz", str(PUBLIC_TEST), "--output-npy", str(step2_out),
        ]
        proc2 = subprocess.run(step2_cmd, capture_output=True, text=True, timeout=300)
        if proc2.returncode != 0:
            raise AssertionError(
                f"Step 2 inference failed.\nstderr={proc2.stderr}"
            )
        step2_preds = load_preds(step2_out, n)
        step2_acc = float((step2_preds == labels).mean())

        # Run step 3 inference
        step3_out = tmp / "step3_preds.npy"
        run_infer(PUBLIC_TEST, step3_out)
        step3_preds = load_preds(step3_out, n)
        step3_acc = float((step3_preds == labels).mean())

    assert step3_acc > step2_acc, (
        f"Step 3 accuracy ({step3_acc:.4f}) must exceed step 2 ({step2_acc:.4f})"
    )


def test_step3_cargo_project_present() -> None:
    """Verify the Cargo project exists and depends on burn."""
    if not CARGO_TOML.exists():
        raise AssertionError(f"Missing Cargo.toml at {CARGO_TOML}")

    cargo_text = CARGO_TOML.read_text(encoding="utf-8")
    cargo_lower = cargo_text.lower()
    if "burn" not in cargo_lower:
        raise AssertionError("Cargo.toml must declare 'burn' as a dependency")
    if "0.20" not in cargo_text:
        raise AssertionError(
            'Cargo.toml must use burn version 0.20 (e.g. burn = "0.20")'
        )


def test_step3_required_outputs_present() -> None:
    if not OPT_PUBLIC_PREDS.exists():
        raise AssertionError(f"missing required file: {OPT_PUBLIC_PREDS}")


def test_step3_public_accuracy_target() -> None:
    labels = np.load(PUBLIC_TEST)["test_labels"].astype(np.int64)
    opt_preds = load_preds(OPT_PUBLIC_PREDS, labels.shape[0])
    opt_acc = float((opt_preds == labels).mean())
    assert opt_acc >= MIN_PUBLIC_ACC, (
        f"optimized public accuracy {opt_acc:.4f} below {MIN_PUBLIC_ACC:.2f}"
    )


def test_step3_inference_command_reproduces_public_preds() -> None:
    """Run cargo run --release and verify output matches saved predictions."""
    labels = np.load(PUBLIC_TEST)["test_labels"].astype(np.int64)
    expected = load_preds(OPT_PUBLIC_PREDS, labels.shape[0])

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "public_preds.npy"
        run_infer(PUBLIC_TEST, out_path)
        inferred = load_preds(out_path, labels.shape[0])

    if not np.array_equal(inferred, expected):
        raise AssertionError(
            "cargo run inference output on public test must match optimized_public_test_preds.npy"
        )


def test_step3_cargo_builds_release() -> None:
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


def test_step3_no_python_shelling() -> None:
    """Verify that Rust source files do not shell out to Python."""
    src_dir = CARGO_PROJECT / "src"
    if not src_dir.exists():
        raise AssertionError(f"Missing Rust source directory: {src_dir}")
    forbidden = ["Command::new(\"python\"", "Command::new(\"python3\"", "std::process::Command"]
    for rs_file in src_dir.rglob("*.rs"):
        source = rs_file.read_text(encoding="utf-8")
        for pattern in forbidden:
            if pattern in source:
                raise AssertionError(
                    f"{rs_file.name} must not shell out to Python. "
                    f"Found: {pattern!r}"
                )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
