#!/usr/bin/env python3

import hashlib
import subprocess
import tempfile
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent
STEP1_FILES = Path("/app/step_1/files")

ONNX_FILE = STEP1_FILES / "model.onnx"
INFER_SCRIPT = STEP1_FILES / "infer.py"

HIDDEN_VAL_IMAGES = BASE / "hidden_val_images.npz"
HIDDEN_VAL_LABELS = BASE / "hidden_val_labels.npy"

HIDDEN_VAL_IMAGES_SHA256 = (
    "01e1178993fbe8e34b07a51223b128f90ca2b3253bbf1e81dfffed981bf8762c"
)
HIDDEN_VAL_LABELS_SHA256 = (
    "f1f5e9f46a6143f574157830aab392dce428002ed13bfe2ff79e19cc46f3a66e"
)

MIN_HIDDEN_VAL_ACC = 0.55


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


def run_infer(model_path: Path, input_npz: Path, output_npy: Path) -> None:
    argv = [
        "python3",
        str(INFER_SCRIPT),
        "--model",
        str(model_path),
        "--input-npz",
        str(input_npz),
        "--output-npy",
        str(output_npy),
    ]
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(
            "Step 1 hidden inference command failed. "
            f"cmd={argv}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )


def test_hidden_inputs_and_labels_integrity() -> None:
    assert sha256_file(HIDDEN_VAL_IMAGES) == HIDDEN_VAL_IMAGES_SHA256
    assert sha256_file(HIDDEN_VAL_LABELS) == HIDDEN_VAL_LABELS_SHA256


def test_hidden_validation_accuracy() -> None:
    labels = np.load(HIDDEN_VAL_LABELS).astype(np.int64)
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "hidden_val_preds.npy"
        run_infer(ONNX_FILE, HIDDEN_VAL_IMAGES, out_path)
        preds = load_preds(out_path, labels.shape[0])
    acc = float((preds == labels).mean())
    assert acc >= MIN_HIDDEN_VAL_ACC, (
        f"hidden validation accuracy {acc:.4f} is below {MIN_HIDDEN_VAL_ACC:.2f}"
    )


def test_hidden_inference_deterministic() -> None:
    """Run inference twice on hidden data and verify predictions are identical."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path_1 = Path(tmp_dir) / "hidden_preds_run1.npy"
        out_path_2 = Path(tmp_dir) / "hidden_preds_run2.npy"
        run_infer(ONNX_FILE, HIDDEN_VAL_IMAGES, out_path_1)
        run_infer(ONNX_FILE, HIDDEN_VAL_IMAGES, out_path_2)
        preds_1 = np.load(out_path_1)
        preds_2 = np.load(out_path_2)
    assert np.array_equal(preds_1, preds_2), (
        "Inference is non-deterministic: two runs on the same hidden data produced different predictions"
    )


def test_hidden_no_torch_at_inference() -> None:
    """Verify that infer.py does not import torch — step 1 requires ONNX inference."""
    if not INFER_SCRIPT.exists():
        raise AssertionError(f"Missing inference script: {INFER_SCRIPT}")
    source = INFER_SCRIPT.read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        # Skip comments and empty lines
        if stripped.startswith("#") or not stripped:
            continue
        if "import torch" in stripped or "from torch" in stripped:
            raise AssertionError(
                f"infer.py must not import torch (ONNX-only inference required). "
                f"Found: {stripped!r}"
            )


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
