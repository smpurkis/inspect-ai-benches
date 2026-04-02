#!/usr/bin/env python3

import importlib
import subprocess
import tempfile
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent

PUBLIC_TEST = BASE / "cifar_public_test.npz"

ONNX_FILE = BASE / "model.onnx"
INFER_SCRIPT = BASE / "infer.py"

MIN_PUBLIC_ACC = 0.65
MAX_MODEL_BYTES = 100_000

NN_OPS = {"Conv", "Gemm", "MatMul", "ConvTranspose"}


def require_file(path: Path) -> Path:
    if not path.exists():
        raise AssertionError(f"Missing required file: {path}")
    return path


def load_pred_array(path: Path, expected_shape: tuple[int, ...]) -> np.ndarray:
    arr = np.load(path)
    if arr.shape != expected_shape:
        raise AssertionError(
            f"{path.name} shape mismatch: got {arr.shape}, expected {expected_shape}"
        )
    if not np.issubdtype(arr.dtype, np.integer):
        raise AssertionError(f"{path.name} dtype must be integer, got {arr.dtype}")
    if int(arr.min()) < 0 or int(arr.max()) > 9:
        raise AssertionError(f"{path.name} contains class IDs outside [0, 9]")
    return arr.astype(np.int64)


def run_infer(model_path: Path, input_npz: Path, output_npy: Path) -> None:
    cmd = [
        "python3",
        str(INFER_SCRIPT),
        "--model",
        str(model_path),
        "--input-npz",
        str(input_npz),
        "--output-npy",
        str(output_npy),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(
            "Inference command failed. "
            f"cmd={' '.join(cmd)}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )


def test_valid_trained_model() -> None:
    """Model pipeline: ONNX file valid, under size limit, contains real NN layers."""
    require_file(ONNX_FILE)
    require_file(INFER_SCRIPT)

    model_size = ONNX_FILE.stat().st_size
    if model_size > MAX_MODEL_BYTES:
        raise AssertionError(
            f"model.onnx is {model_size:,} bytes, exceeds limit of {MAX_MODEL_BYTES:,} bytes"
        )

    onnx = importlib.import_module("onnx")
    model = onnx.load(str(ONNX_FILE))
    onnx.checker.check_model(model)

    # Verify model contains real neural network operations
    op_types = {node.op_type for node in model.graph.node}
    if not op_types & NN_OPS:
        raise AssertionError(
            f"model.onnx has no neural network layers (found ops: {op_types}). "
            f"Expected at least one of: {NN_OPS}"
        )

    # Verify infer.py uses onnxruntime
    source = INFER_SCRIPT.read_text(encoding="utf-8")
    if "onnxruntime" not in source and "onnx" not in source:
        raise AssertionError(
            "infer.py must use onnxruntime for inference, not torch"
        )


def test_public_accuracy() -> None:
    """Run inference on public test set and verify accuracy >= 60%."""
    labels = np.load(PUBLIC_TEST)["test_labels"].astype(np.int64)

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "public_preds.npy"
        run_infer(ONNX_FILE, PUBLIC_TEST, out_path)
        preds = load_pred_array(out_path, (labels.shape[0],))

    acc = float((preds == labels).mean())
    assert acc >= MIN_PUBLIC_ACC, (
        f"public accuracy {acc:.4f} is below {MIN_PUBLIC_ACC:.2f}"
    )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
