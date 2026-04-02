#!/usr/bin/env python3

import hashlib
import subprocess
import tempfile
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent
FILES = Path("/app/files")

CARGO_TOML = FILES / "cifar-infer" / "Cargo.toml"

# Hidden data lives in hidden/ — re-injected during testing
HIDDEN_VAL_IMAGES = Path("/app/hidden/hidden_val_images.npz")
HIDDEN_VAL_LABELS = Path("/app/hidden/hidden_val_labels.npy")

HIDDEN_VAL_IMAGES_SHA256 = (
    "62b2de3d2569d42464bf34c5f60ce348bea1aa7a3281f52fcf688b96562c71a2"
)
HIDDEN_VAL_LABELS_SHA256 = (
    "a6c3f5745102ff89d3b0aaae489b2ed1091ead149117bd66fe8ba649ff975eba"
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
            "Hidden inference via cargo run failed. "
            f"cmd={cmd}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )


def test_hidden_no_hardcoded_predictions() -> None:
    """Rust source must not embed hardcoded prediction arrays or raw .npy data."""
    src_dir = FILES / "cifar-infer" / "src"
    if not src_dir.exists():
        raise AssertionError(f"Missing Rust source directory: {src_dir}")
    import re
    long_array_pattern = re.compile(r"\[\s*\d+\s*(?:,\s*\d+\s*){19,}\]")
    for rs_file in src_dir.rglob("*.rs"):
        source = rs_file.read_text(encoding="utf-8")
        matches = long_array_pattern.findall(source)
        assert not matches, (
            f"{rs_file.name} contains a suspiciously long integer array literal "
            f"({len(matches)} match(es)) — predictions must come from the model, "
            f"not hardcoded arrays"
        )
        # Also check for embedded .npy magic bytes (raw numpy file content)
        raw = rs_file.read_bytes()
        assert b"\\x93NUMPY" not in raw and b"\x93NUMPY" not in raw, (
            f"{rs_file.name} appears to embed raw .npy data"
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


def test_hidden_burn_actually_used() -> None:
    """Rust source must actually use the burn crate, not just list it as a dependency."""
    src_dir = FILES / "cifar-infer" / "src"
    if not src_dir.exists():
        raise AssertionError(f"Missing Rust source directory: {src_dir}")
    all_source = ""
    for rs_file in src_dir.rglob("*.rs"):
        all_source += rs_file.read_text(encoding="utf-8")
    assert "use burn" in all_source or "burn::" in all_source, (
        "Rust source does not use the burn crate — inference must be implemented with burn, "
        "not just listed as a Cargo dependency"
    )


def test_hidden_no_python_shelling() -> None:
    """Verify that Rust source files do not shell out to Python."""
    src_dir = FILES / "cifar-infer" / "src"
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
