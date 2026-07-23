#!/usr/bin/env python3

import hashlib
import os
import re
import subprocess
import tempfile
import tomllib
from pathlib import Path

import numpy as np


FILES = Path("/app/files")
PROJECT = FILES / "cifar-infer"
MANIFEST = PROJECT / "Cargo.toml"
MODEL = PROJECT / "model.mpk"
TRAIN_BINARY = PROJECT / "target" / "release" / "cifar-train"
INFER_BINARY = PROJECT / "target" / "release" / "cifar-infer"
TRAIN_FIXTURE = FILES / "cifar_tiny.npz"
TRAIN_CONFIG = PROJECT / "training.toml"
HIDDEN_IMAGES = Path("/app/hidden/hidden_val_images.npz")
HIDDEN_LABELS = Path("/app/hidden/hidden_val_labels.npy")

HIDDEN_IMAGES_SHA256 = "62b2de3d2569d42464bf34c5f60ce348bea1aa7a3281f52fcf688b96562c71a2"
HIDDEN_LABELS_SHA256 = "a6c3f5745102ff89d3b0aaae489b2ed1091ead149117bd66fe8ba649ff975eba"
MIN_ACCURACY = 0.60
MAX_COMMAND_OUTPUT_BYTES = 4096
MAX_HIDDEN_PREDICTION_BYTES = 2048
TRAINING_TIMEOUT_SECONDS = 1200
INFERENCE_TIMEOUT_SECONDS = 120

ENV = {
    **os.environ,
    "CARGO_NET_OFFLINE": "true",
    "RAYON_NUM_THREADS": "8",
    "OMP_NUM_THREADS": "8",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounded_run(command: list[str], timeout: int, description: str) -> None:
    try:
        proc = subprocess.run(command, capture_output=True, timeout=timeout, env=ENV)
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(f"{description} exceeded its {timeout}-second limit") from exc
    output_size = len(proc.stdout) + len(proc.stderr)
    assert output_size <= MAX_COMMAND_OUTPUT_BYTES, (
        f"{description} emitted {output_size} bytes; limit is "
        f"{MAX_COMMAND_OUTPUT_BYTES}"
    )
    assert proc.returncode == 0, (
        f"{description} failed with status {proc.returncode}\n"
        f"stdout={proc.stdout.decode(errors='replace')}\n"
        f"stderr={proc.stderr.decode(errors='replace')}"
    )


def run_infer(input_path: Path, output_path: Path) -> None:
    bounded_run(
        [
            "timeout",
            "--signal=KILL",
            f"{INFERENCE_TIMEOUT_SECONDS}s",
            str(INFER_BINARY),
            "--input-npz",
            str(input_path),
            "--output-npy",
            str(output_path),
        ],
        INFERENCE_TIMEOUT_SECONDS + 10,
        "hidden inference",
    )


def run_train() -> None:
    bounded_run(
        [
            "timeout",
            "--signal=KILL",
            f"{TRAINING_TIMEOUT_SECONDS}s",
            str(TRAIN_BINARY),
            "--train-npz",
            str(TRAIN_FIXTURE),
            "--config",
            str(TRAIN_CONFIG),
            "--model-out",
            str(MODEL),
        ],
        TRAINING_TIMEOUT_SECONDS + 10,
        "repeat training",
    )


def load_preds(path: Path, expected_len: int) -> np.ndarray:
    assert path.is_file() and not path.is_symlink(), f"Missing predictions: {path}"
    assert path.stat().st_size <= MAX_HIDDEN_PREDICTION_BYTES
    values = np.load(path, allow_pickle=False)
    assert values.shape == (expected_len,)
    assert values.dtype == np.uint8
    assert int(values.min()) >= 0 and int(values.max()) <= 9
    return values


def accuracy(predictions: np.ndarray, labels: np.ndarray, split: str) -> None:
    score = float((predictions.astype(np.int64) == labels).mean())
    assert score >= MIN_ACCURACY, (
        f"{split} accuracy {score:.4f} is below {MIN_ACCURACY:.2f}"
    )


def test_hidden_fixture_integrity() -> None:
    assert sha256_file(HIDDEN_IMAGES) == HIDDEN_IMAGES_SHA256
    assert sha256_file(HIDDEN_LABELS) == HIDDEN_LABELS_SHA256


def test_project_inventory_and_policy() -> None:
    expected = {
        "Cargo.toml",
        "src/main.rs",
        "src/model.rs",
        "src/train.rs",
        "training.toml",
    }
    optional_generated = {"Cargo.lock", "model.mpk"}
    found = set()
    for path in PROJECT.rglob("*"):
        relative = path.relative_to(PROJECT)
        if "target" in relative.parts:
            continue
        assert not path.is_symlink(), f"Project may not contain symlinks: {relative}"
        if path.is_file():
            found.add(relative.as_posix())
    assert expected <= found, f"Missing starter project files: {sorted(expected - found)}"
    assert found <= expected | optional_generated, (
        f"Unexpected project files: {sorted(found - expected - optional_generated)}"
    )

    manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    assert set(manifest.get("dependencies", {})) == {
        "burn",
        "ndarray",
        "ndarray-npy",
    }, "Only the fixed Burn and NumPy-format dependencies are allowed"
    burn_dep = manifest["dependencies"]["burn"]
    assert burn_dep.get("version") == "=0.20.0", "Burn must remain pinned to 0.20.0"
    assert burn_dep.get("default-features") is False
    assert set(burn_dep.get("features", [])) == {"std", "ndarray", "autodiff"}, (
        "Burn must use only the fixed CPU/autodiff feature set"
    )
    assert manifest.get("package", {}).get("build") in (None, False), (
        "Cargo build scripts are forbidden"
    )

    forbidden = {
        "python": "Python delegation",
        "pyo3": "Python delegation",
        "std::process": "subprocess delegation",
        "command::new": "subprocess delegation",
        "std::net": "network access",
        "tcpstream": "network access",
        "udpsocket": "network access",
        "reqwest": "network access",
        "ureq": "network access",
        "curl": "network access",
        "wget": "network access",
        "http://": "network access",
        "https://": "network access",
        "include_bytes!": "embedded artifact delegation",
        "include_str!": "embedded artifact delegation",
        "pretrained": "pretrained/runtime delegation",
        "onnx": "pretrained/runtime delegation",
        "safetensors": "pretrained/runtime delegation",
        "torch": "pretrained/runtime delegation",
        "candle": "alternate model runtime",
    }
    text_paths = [MANIFEST, PROJECT / "training.toml"] + sorted(
        (PROJECT / "src").glob("*.rs")
    )
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in text_paths
    ).lower()
    assert "burn::" in source or "use burn" in source, "Rust source must use Burn"
    for token, reason in forbidden.items():
        assert token not in source, f"Forbidden {reason} token found: {token}"
    long_literal = re.compile(r"\[\s*-?\d+(?:\.\d+)?\s*(?:,\s*-?\d+(?:\.\d+)?\s*){31,}\]")
    assert not long_literal.search(source), "Large embedded numeric artifacts are forbidden"


def test_hidden_accuracy() -> None:
    labels = np.load(HIDDEN_LABELS, allow_pickle=False).astype(np.int64)
    with tempfile.TemporaryDirectory() as tmp_dir:
        output = Path(tmp_dir) / "hidden.npy"
        run_infer(HIDDEN_IMAGES, output)
        predictions = load_preds(output, labels.shape[0])
    accuracy(predictions, labels, "hidden")


def test_training_and_prediction_hashes_are_deterministic() -> None:
    labels = np.load(HIDDEN_LABELS, allow_pickle=False)
    with tempfile.TemporaryDirectory() as tmp_dir:
        before_predictions = Path(tmp_dir) / "before.npy"
        after_predictions = Path(tmp_dir) / "after.npy"
        run_infer(HIDDEN_IMAGES, before_predictions)
        model_hash = sha256_file(MODEL)
        run_train()
        assert sha256_file(MODEL) == model_hash, (
            "Two training runs produced different model.mpk hashes"
        )
        run_infer(HIDDEN_IMAGES, after_predictions)
        load_preds(before_predictions, labels.shape[0])
        load_preds(after_predictions, labels.shape[0])
        assert sha256_file(before_predictions) == sha256_file(after_predictions), (
            "Predictions changed after deterministic retraining"
        )


def test_permuted_perturbed_hidden_accuracy() -> None:
    source = np.load(HIDDEN_IMAGES, allow_pickle=False)["test_images"]
    labels = np.load(HIDDEN_LABELS, allow_pickle=False).astype(np.int64)
    permutation = np.random.default_rng(20260328).permutation(labels.shape[0])
    perturbed = np.clip(source[permutation] * np.float32(0.98) + np.float32(0.01), 0, 1)
    perturbed = np.ascontiguousarray(perturbed, dtype=np.float32)
    expected = labels[permutation]

    with tempfile.TemporaryDirectory() as tmp_dir:
        fixture = Path(tmp_dir) / "perturbed_hidden.npz"
        output = Path(tmp_dir) / "perturbed_hidden.npy"
        np.savez_compressed(fixture, test_images=perturbed)
        run_infer(fixture, output)
        predictions = load_preds(output, expected.shape[0])
    accuracy(predictions, expected, "permuted perturbed hidden")


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
