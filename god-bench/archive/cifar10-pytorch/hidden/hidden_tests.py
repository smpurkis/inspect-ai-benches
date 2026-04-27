#!/usr/bin/env python3

import hashlib
import importlib
import subprocess
import tempfile
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent
FILES = Path("/app/files")

ONNX_FILE = FILES / "model.onnx"
INFER_SCRIPT = FILES / "infer.py"

HIDDEN_VAL_IMAGES = BASE / "hidden_val_images.npz"
HIDDEN_VAL_LABELS = BASE / "hidden_val_labels.npy"

HIDDEN_VAL_IMAGES_SHA256 = (
    "01e1178993fbe8e34b07a51223b128f90ca2b3253bbf1e81dfffed981bf8762c"
)
HIDDEN_VAL_LABELS_SHA256 = (
    "f1f5e9f46a6143f574157830aab392dce428002ed13bfe2ff79e19cc46f3a66e"
)

MIN_HIDDEN_VAL_ACC = 0.63


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
            "Hidden inference command failed. "
            f"cmd={argv}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )


def test_hidden_accuracy() -> None:
    """Hidden validation accuracy >= 60%, deterministic, no torch import."""
    if not INFER_SCRIPT.exists():
        raise AssertionError(f"Missing inference script: {INFER_SCRIPT}")

    # Verify no torch import
    source = INFER_SCRIPT.read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if "import torch" in stripped or "from torch" in stripped:
            raise AssertionError(
                f"infer.py must not import torch (ONNX-only inference required). "
                f"Found: {stripped!r}"
            )

    labels = np.load(HIDDEN_VAL_LABELS).astype(np.int64)

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path_1 = Path(tmp_dir) / "hidden_preds_run1.npy"
        out_path_2 = Path(tmp_dir) / "hidden_preds_run2.npy"
        run_infer(ONNX_FILE, HIDDEN_VAL_IMAGES, out_path_1)
        run_infer(ONNX_FILE, HIDDEN_VAL_IMAGES, out_path_2)
        preds_1 = load_preds(out_path_1, labels.shape[0])
        preds_2 = load_preds(out_path_2, labels.shape[0])

    assert np.array_equal(preds_1, preds_2), (
        "Inference is non-deterministic: two runs produced different predictions"
    )

    acc = float((preds_1 == labels).mean())
    assert acc >= MIN_HIDDEN_VAL_ACC, (
        f"hidden validation accuracy {acc:.4f} is below {MIN_HIDDEN_VAL_ACC:.2f}"
    )


def test_model_has_trained_weights() -> None:
    """ONNX model must contain real trained weight tensors."""
    if not ONNX_FILE.exists():
        raise AssertionError(f"Missing model: {ONNX_FILE}")

    onnx = importlib.import_module("onnx")
    from onnx import numpy_helper

    model = onnx.load(str(ONNX_FILE))

    if len(model.graph.initializer) == 0:
        raise AssertionError(
            "model.onnx has no initializer tensors — a trained model must contain weights"
        )

    max_std = 0.0
    max_size = 0
    for init in model.graph.initializer:
        arr = numpy_helper.to_array(init)
        max_size = max(max_size, arr.size)
        if arr.size > 1:
            max_std = max(max_std, float(np.std(arr)))

    if max_size < 10:
        raise AssertionError(
            f"Largest weight tensor has only {max_size} elements — too small for a real model"
        )
    if max_std < 0.001:
        raise AssertionError(
            f"All weight tensors have near-zero std ({max_std:.6f}) — model appears untrained"
        )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
