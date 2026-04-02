#!/usr/bin/env python3

import hashlib
import subprocess
import tempfile
from pathlib import Path


BASE = Path(__file__).resolve().parent
STEP1_HIDDEN = BASE.parent.parent / "step_1" / "hidden"
RUNNER = BASE.parent / "files" / "run_wasm_codec.sh"
WAT = BASE.parent / "files" / "quiltpress_wasi.wat"
TEST_FULL = STEP1_HIDDEN / "test_full.txt"
TEST_PDF = STEP1_HIDDEN / "test.pdf"

TEST_FULL_SHA256 = "7b57ff0334e57b1f3e62ddc59e03cdcad7efe7c22a61fcc79975b9b4b0b4e1be"
TEST_PDF_SHA256 = "d937cf6c07c7540387e74e369b1c776098da0b6e260f421035c852534ec82ccd"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_runner(*args: str) -> None:
    cmd = ["bash", str(RUNNER), *args]
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            "runner command failed\n"
            f"cmd: {cmd}\n"
            f"returncode: {exc.returncode}\n"
            f"stdout:\n{exc.stdout}\n"
            f"stderr:\n{exc.stderr}"
        ) from exc


def _roundtrip(path: Path, tmpdir: Path) -> tuple[bytes, bytes, bytes]:
    """Compress and decompress, returning (original, decoded, encoded)."""
    compressed = tmpdir / (path.name + ".qtp")
    restored = tmpdir / (path.name + ".roundtrip")

    run_runner("compress", str(path), str(compressed))
    run_runner("decompress", str(compressed), str(restored))

    return path.read_bytes(), restored.read_bytes(), compressed.read_bytes()


def test_hidden_cross_codec_wasm_compress_python_decompress() -> None:
    """Compress with step 2 WASM runner, decompress with step 1 Python reference codec.

    Proves format compatibility between the WASM and Python implementations."""
    import importlib.util

    ref_path = STEP1_HIDDEN / "quiltpress_q1_reference.py"
    spec = importlib.util.spec_from_file_location("quiltpress_q1_reference", ref_path)
    assert spec is not None and spec.loader is not None
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        compressed = tmp / "cross_codec.qtp"
        run_runner("compress", str(TEST_FULL), str(compressed))

        original = TEST_FULL.read_bytes()
        blob = compressed.read_bytes()
        decoded = ref.decompress_bytes(blob)
        assert decoded == original, (
            "cross-codec failed: WASM compress then Python reference decompress "
            "produced different output"
        )


def test_hidden_roundtrip_text() -> None:
    """test_full.txt roundtrip correctness and compression ratio."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original, decoded, encoded = _roundtrip(TEST_FULL, Path(tmpdir))
        assert decoded == original, "text roundtrip mismatch"
        assert len(encoded) < len(original), (
            f"text compressed size {len(encoded)} >= original {len(original)}"
        )


def test_hidden_roundtrip_pdf() -> None:
    """test.pdf roundtrip correctness and compression ratio."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original, decoded, encoded = _roundtrip(TEST_PDF, Path(tmpdir))
        assert decoded == original, "pdf roundtrip mismatch"
        assert len(encoded) < len(original), (
            f"pdf compressed size {len(encoded)} >= original {len(original)}"
        )


def test_hidden_deterministic_output() -> None:
    """Run compression twice, check byte-identical output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        out_a = tmp / "a.qtp"
        out_b = tmp / "b.qtp"

        run_runner("compress", str(TEST_FULL), str(out_a))
        run_runner("compress", str(TEST_FULL), str(out_b))
        assert out_a.read_bytes() == out_b.read_bytes(), (
            "compression output is not deterministic"
        )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
