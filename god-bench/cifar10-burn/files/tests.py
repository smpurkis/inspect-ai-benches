#!/usr/bin/env python3

import hashlib
import json
import os
import re
import subprocess
import tempfile
import tomllib
from pathlib import Path

import numpy as np


FILES = Path(__file__).resolve().parent
PROJECT = FILES / "cifar-infer"
MANIFEST = PROJECT / "Cargo.toml"
MODEL = PROJECT / "model.mpk"
BINARY = PROJECT / "target" / "release" / "cifar-infer"
PUBLIC_FIXTURE = FILES / "cifar_public_test.npz"
TRAIN_FIXTURE = FILES / "cifar_tiny.npz"
PUBLIC_PREDS = FILES / "burn_public_test_preds.npy"

PUBLIC_SHA256 = "f3548cb190158b2e09db31d86e9f2e670778c9b19c53d793d7778ecee20d595b"
TRAIN_SHA256 = "3a2c79eecb6ecf676cab7a661e40861421a8e8378052dff574ec1665685ca70b"
MIN_ACCURACY = 0.60
MAX_MODEL_BYTES = 100_000_000
MAX_COMMAND_OUTPUT_BYTES = 4096
MAX_PUBLIC_PREDICTION_BYTES = 4096
BUILD_TIMEOUT_SECONDS = 300
INFERENCE_TIMEOUT_SECONDS = 120

ENV = {
    **os.environ,
    "CARGO_NET_OFFLINE": "true",
    "CARGO_TARGET_DIR": str(PROJECT / "target"),
    "RAYON_NUM_THREADS": "8",
    "OMP_NUM_THREADS": "8",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounded_run(command: list[str], timeout: int, description: str) -> None:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            env=ENV,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(f"{description} exceeded {timeout} seconds") from exc
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


def run_infer(input_npz: Path, output_npy: Path) -> None:
    bounded_run(
        [
            "timeout",
            "--signal=KILL",
            f"{INFERENCE_TIMEOUT_SECONDS}s",
            str(BINARY),
            "--input-npz",
            str(input_npz),
            "--output-npy",
            str(output_npy),
        ],
        INFERENCE_TIMEOUT_SECONDS + 10,
        "inference",
    )


def load_preds(path: Path, expected_len: int, max_bytes: int) -> np.ndarray:
    assert path.is_file() and not path.is_symlink(), f"Missing prediction file: {path}"
    assert path.stat().st_size <= max_bytes, (
        f"{path.name} is {path.stat().st_size} bytes; limit is {max_bytes}"
    )
    arr = np.load(path, allow_pickle=False)
    assert arr.shape == (expected_len,), (
        f"{path.name} shape is {arr.shape}; expected {(expected_len,)}"
    )
    assert arr.dtype == np.uint8, f"{path.name} dtype must be uint8, got {arr.dtype}"
    assert int(arr.min()) >= 0 and int(arr.max()) <= 9, (
        f"{path.name} has class IDs outside [0, 9]"
    )
    return arr


def test_fixture_integrity() -> None:
    assert sha256_file(TRAIN_FIXTURE) == TRAIN_SHA256, "Training fixture was modified"
    assert sha256_file(PUBLIC_FIXTURE) == PUBLIC_SHA256, "Public fixture was modified"


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


def test_cargo_metadata_has_no_build_script() -> None:
    proc = subprocess.run(
        [
            "cargo",
            "metadata",
            "--offline",
            "--no-deps",
            "--format-version=1",
            "--manifest-path",
            str(MANIFEST),
        ],
        capture_output=True,
        timeout=30,
        env=ENV,
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    assert len(proc.stdout) + len(proc.stderr) <= MAX_COMMAND_OUTPUT_BYTES * 4
    metadata = json.loads(proc.stdout)
    root = next(package for package in metadata["packages"] if package["name"] == "cifar-infer")
    assert {target["name"] for target in root["targets"]} == {
        "cifar-infer",
        "cifar-train",
    }
    assert all("custom-build" not in target["kind"] for target in root["targets"])


def test_cargo_builds_release_offline() -> None:
    bounded_run(
        [
            "cargo",
            "build",
            "--quiet",
            "--release",
            "--locked",
            "--offline",
            "--manifest-path",
            str(MANIFEST),
        ],
        BUILD_TIMEOUT_SECONDS,
        "offline cargo build",
    )


def test_model_and_public_accuracy() -> None:
    assert MODEL.is_file() and not MODEL.is_symlink(), f"Missing model record: {MODEL}"
    assert 1000 < MODEL.stat().st_size <= MAX_MODEL_BYTES, (
        f"model.mpk size {MODEL.stat().st_size} is outside (1000, {MAX_MODEL_BYTES}]"
    )
    labels = np.load(PUBLIC_FIXTURE, allow_pickle=False)["test_labels"]
    preds = load_preds(PUBLIC_PREDS, labels.shape[0], MAX_PUBLIC_PREDICTION_BYTES)
    accuracy = float((preds.astype(np.int64) == labels).mean())
    assert accuracy >= MIN_ACCURACY, (
        f"public accuracy {accuracy:.4f} is below {MIN_ACCURACY:.2f}"
    )


def test_public_inference_hash_is_deterministic() -> None:
    labels = np.load(PUBLIC_FIXTURE, allow_pickle=False)["test_labels"]
    expected = load_preds(PUBLIC_PREDS, labels.shape[0], MAX_PUBLIC_PREDICTION_BYTES)
    model_hash = sha256_file(MODEL)
    with tempfile.TemporaryDirectory() as tmp_dir:
        first = Path(tmp_dir) / "first.npy"
        second = Path(tmp_dir) / "second.npy"
        run_infer(PUBLIC_FIXTURE, first)
        run_infer(PUBLIC_FIXTURE, second)
        first_preds = load_preds(first, labels.shape[0], MAX_PUBLIC_PREDICTION_BYTES)
        second_preds = load_preds(second, labels.shape[0], MAX_PUBLIC_PREDICTION_BYTES)
        assert sha256_file(first) == sha256_file(second), (
            "Repeated inference produced different prediction hashes"
        )
    assert np.array_equal(first_preds, expected)
    assert np.array_equal(second_preds, expected)
    assert sha256_file(MODEL) == model_hash, "Inference modified model.mpk"


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
