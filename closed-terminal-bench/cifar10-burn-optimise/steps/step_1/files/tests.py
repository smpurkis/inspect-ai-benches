#!/usr/bin/env python3

import hashlib
import importlib
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent

PUBLIC_TEST = BASE / "cifar_public_test.npz"
TRAIN_CONFIG = BASE / "train_config.json"

ONNX_FILE = BASE / "model.onnx"
INFER_SCRIPT = BASE / "infer.py"
PUBLIC_PREDS = BASE / "pytorch_public_test_preds.npy"

PUBLIC_SHA256 = "f3548cb190158b2e09db31d86e9f2e670778c9b19c53d793d7778ecee20d595b"

# All tuneable constraints live in train_config.json (single source of truth).
_CFG = json.loads(TRAIN_CONFIG.read_text(encoding="utf-8"))
MIN_PUBLIC_ACC = float(_CFG["min_public_acc"])
MAX_PARAMS = int(_CFG["max_params"])
MAX_MODEL_BYTES = int(_CFG["max_model_bytes"])


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
            "Step 1 inference command failed. "
            f"cmd={' '.join(cmd)}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )


def test_step1_dataset_integrity() -> None:
    assert sha256_file(PUBLIC_TEST) == PUBLIC_SHA256


def test_step1_required_outputs_present() -> None:
    require_file(ONNX_FILE)
    require_file(INFER_SCRIPT)
    require_file(PUBLIC_PREDS)

    model_size = ONNX_FILE.stat().st_size
    if model_size < 10_000:
        raise AssertionError("model.onnx is unexpectedly small")
    if model_size > MAX_MODEL_BYTES:
        raise AssertionError(
            f"model.onnx is {model_size:,} bytes, exceeds limit of {MAX_MODEL_BYTES:,} bytes "
            f"(~{MAX_PARAMS:,} params)"
        )

    # Validate ONNX model structure
    onnx = importlib.import_module("onnx")
    model = onnx.load(str(ONNX_FILE))
    onnx.checker.check_model(model)


def test_step1_infer_uses_onnxruntime() -> None:
    """Verify that infer.py uses onnxruntime, not torch, for inference."""
    source = INFER_SCRIPT.read_text(encoding="utf-8")
    if "onnxruntime" not in source and "onnx" not in source:
        raise AssertionError(
            "infer.py must use onnxruntime for inference, not torch"
        )


def test_step1_public_accuracy_threshold() -> None:
    labels = np.load(PUBLIC_TEST)["test_labels"].astype(np.int64)
    preds = load_pred_array(PUBLIC_PREDS, (labels.shape[0],))
    acc = float((preds == labels).mean())
    assert acc >= MIN_PUBLIC_ACC, (
        f"public accuracy {acc:.4f} is below {MIN_PUBLIC_ACC:.2f}"
    )


def test_step1_inference_command_reproduces_public_preds() -> None:
    labels = np.load(PUBLIC_TEST)["test_labels"].astype(np.int64)
    expected = load_pred_array(PUBLIC_PREDS, (labels.shape[0],))

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "public_preds.npy"
        run_infer(ONNX_FILE, PUBLIC_TEST, out_path)
        inferred = load_pred_array(out_path, (labels.shape[0],))

    if not np.array_equal(inferred, expected):
        raise AssertionError(
            "infer.py output on public test must match pytorch_public_test_preds.npy"
        )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
