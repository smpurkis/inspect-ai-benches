#!/usr/bin/env python3

import hashlib
import subprocess
import tempfile
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent
STEP3_FILES = Path("/app/step_3/files")

CARGO_TOML = STEP3_FILES / "cifar-infer" / "Cargo.toml"

# Hidden data lives in step_1/hidden/ — re-injected during step 3 testing
HIDDEN_VAL_IMAGES = Path("/app/step_1/hidden/hidden_val_images.npz")
HIDDEN_VAL_LABELS = Path("/app/step_1/hidden/hidden_val_labels.npy")

HIDDEN_VAL_IMAGES_SHA256 = (
    "01e1178993fbe8e34b07a51223b128f90ca2b3253bbf1e81dfffed981bf8762c"
)
HIDDEN_VAL_LABELS_SHA256 = (
    "f1f5e9f46a6143f574157830aab392dce428002ed13bfe2ff79e19cc46f3a66e"
)
MIN_HIDDEN_VAL_ACC = 0.60


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_preds(path: Path, expected_len: int) -> np.ndarray:
    if not path.exists():
        raise AssertionError(f"Missing predictions: {path}")
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
            "Step 3 hidden inference via cargo run failed. "
            f"cmd={cmd}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )


def test_hidden_accuracy_improvement_over_step2() -> None:
    """Step 3 optimized model must outperform step 2 baseline on hidden validation data."""
    STEP2_CARGO_TOML = Path("/app/step_2/files/cifar-infer/Cargo.toml")
    if not STEP2_CARGO_TOML.exists():
        raise AssertionError(f"Missing step 2 Cargo.toml at {STEP2_CARGO_TOML}")

    labels = np.load(HIDDEN_VAL_LABELS).astype(np.int64)
    n = labels.shape[0]

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        # Run step 2 inference
        step2_out = tmp / "step2_hidden_preds.npy"
        step2_cmd = [
            "cargo", "run", "--release",
            "--manifest-path", str(STEP2_CARGO_TOML),
            "--", "--input-npz", str(HIDDEN_VAL_IMAGES), "--output-npy", str(step2_out),
        ]
        proc2 = subprocess.run(step2_cmd, capture_output=True, text=True, timeout=300)
        if proc2.returncode != 0:
            raise AssertionError(
                f"Step 2 inference failed.\nstderr={proc2.stderr}"
            )
        step2_preds = load_preds(step2_out, n)
        step2_acc = float((step2_preds == labels).mean())

        # Run step 3 inference
        step3_out = tmp / "step3_hidden_preds.npy"
        run_infer(HIDDEN_VAL_IMAGES, step3_out)
        step3_preds = load_preds(step3_out, n)
        step3_acc = float((step3_preds == labels).mean())

    assert step3_acc > step2_acc, (
        f"Step 3 hidden accuracy ({step3_acc:.4f}) must exceed step 2 ({step2_acc:.4f})"
    )


def test_hidden_validation_accuracy() -> None:
    labels = np.load(HIDDEN_VAL_LABELS).astype(np.int64)
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "hidden_val_preds.npy"
        run_infer(HIDDEN_VAL_IMAGES, out_path)
        preds = load_preds(out_path, labels.shape[0])
    acc = float((preds == labels).mean())
    assert acc >= MIN_HIDDEN_VAL_ACC - 0.02, (
        f"hidden validation accuracy {acc:.4f} is below {MIN_HIDDEN_VAL_ACC - 0.02:.2f}"
    )


def test_hidden_inference_deterministic() -> None:
    """Run inference twice on hidden data and verify predictions are identical."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path_1 = Path(tmp_dir) / "hidden_preds_run1.npy"
        out_path_2 = Path(tmp_dir) / "hidden_preds_run2.npy"
        run_infer(HIDDEN_VAL_IMAGES, out_path_1)
        run_infer(HIDDEN_VAL_IMAGES, out_path_2)
        preds_1 = np.load(out_path_1)
        preds_2 = np.load(out_path_2)
    assert np.array_equal(preds_1, preds_2), (
        "Inference is non-deterministic: two runs on the same hidden data produced different predictions"
    )


def test_hidden_no_python_shelling() -> None:
    """Verify that Rust source files do not shell out to Python."""
    src_dir = STEP3_FILES / "cifar-infer" / "src"
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


def test_hidden_cargo_builds_release() -> None:
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
