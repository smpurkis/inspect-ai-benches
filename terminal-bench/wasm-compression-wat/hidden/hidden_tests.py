#!/usr/bin/env python3

import hashlib
import struct
import subprocess
import tempfile
from pathlib import Path

import pytest


BASE = Path(__file__).resolve().parent
HIDDEN_DIR = BASE
RUNNER = BASE.parent / "files" / "run_wasm_codec.sh"
WAT = BASE.parent / "files" / "quiltpress_wasi.wat"
TEST_FULL = HIDDEN_DIR / "test_full.txt"
TEST_PDF = HIDDEN_DIR / "test.pdf"

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
    """Compress with WASM runner, decompress with Python reference codec.

    Proves format compatibility between the WASM and Python implementations."""
    import importlib.util

    ref_path = HIDDEN_DIR / "quiltpress_q1_reference.py"
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


# ---------------------------------------------------------------------------
# Anti-cheat: WAT source must not contain hardcoded file paths
# ---------------------------------------------------------------------------

def test_wat_no_hardcoded_paths() -> None:
    """WAT source must not contain hardcoded paths to test files."""
    wat_path = BASE.parent / "files" / "quiltpress_wasi.wat"
    if not wat_path.exists():
        pytest.skip("WAT file not found")
    content = wat_path.read_text(errors="replace").lower()
    suspicious = ["test.txt", "test_full", "test.pdf", "/app/files/test",
                   "/app/hidden", "quiltpress_q1"]
    for s in suspicious:
        assert s not in content, (
            f"WAT source contains suspicious hardcoded string: {s!r}"
        )


# ---------------------------------------------------------------------------
# Anti-cheat: different inputs produce different compressed outputs
# ---------------------------------------------------------------------------

def test_different_inputs_different_compressed() -> None:
    """Two different inputs must produce different compressed blobs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        data_a = b"aaaaa" * 100
        data_b = b"bbbbb" * 100

        inp_a = tmp / "a.bin"
        inp_b = tmp / "b.bin"
        inp_a.write_bytes(data_a)
        inp_b.write_bytes(data_b)

        comp_a = tmp / "a.qtp"
        comp_b = tmp / "b.qtp"
        run_runner("compress", str(inp_a), str(comp_a))
        run_runner("compress", str(inp_b), str(comp_b))

        assert comp_a.read_bytes() != comp_b.read_bytes(), (
            "Different inputs produced identical compressed outputs"
        )


# ---------------------------------------------------------------------------
# Anti-cheat: cross-codec reverse direction (Python compress -> WASM decompress)
# ---------------------------------------------------------------------------

def test_cross_codec_python_compress_wasm_decompress() -> None:
    """Compress with Python reference, decompress with WASM runner."""
    import importlib.util

    ref_path = HIDDEN_DIR / "quiltpress_q1_reference.py"
    spec = importlib.util.spec_from_file_location("quiltpress_q1_ref2", ref_path)
    assert spec is not None and spec.loader is not None
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)

    original = b"The quick brown fox jumps over the lazy dog. " * 50
    compressed = ref.compress_bytes(original)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        comp_file = tmp / "py_compressed.qtp"
        comp_file.write_bytes(compressed)
        restored_file = tmp / "py_restored.bin"
        run_runner("decompress", str(comp_file), str(restored_file))
        assert restored_file.read_bytes() == original, (
            "Python compress -> WASM decompress produced different output"
        )


# ---------------------------------------------------------------------------
# Difficulty: roundtrip on binary data with all byte values
# ---------------------------------------------------------------------------

def test_roundtrip_binary_all_bytes() -> None:
    """Roundtrip on data containing all 256 byte values."""
    data = bytes(range(256)) * 10
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        inp = tmp / "allbytes.bin"
        inp.write_bytes(data)
        comp = tmp / "allbytes.qtp"
        rest = tmp / "allbytes.out"
        run_runner("compress", str(inp), str(comp))
        run_runner("decompress", str(comp), str(rest))
        assert rest.read_bytes() == data, "roundtrip failed on all-bytes data"


# ---------------------------------------------------------------------------
# Difficulty: roundtrip on large repetitive data
# ---------------------------------------------------------------------------

def test_roundtrip_large_repetitive() -> None:
    """Roundtrip on 10KB of repetitive data."""
    data = b"abcde" * 2000
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        inp = tmp / "large.bin"
        inp.write_bytes(data)
        comp = tmp / "large.qtp"
        rest = tmp / "large.out"
        run_runner("compress", str(inp), str(comp))
        run_runner("decompress", str(comp), str(rest))
        assert rest.read_bytes() == data, "roundtrip failed on large repetitive data"


# ---------------------------------------------------------------------------
# Difficulty: compression ratio on repetitive data
# ---------------------------------------------------------------------------

def test_compression_ratio_repetitive() -> None:
    """Repetitive data must compress to < 50% of original size."""
    data = b"hello" * 1000  # 5000 bytes, highly repetitive
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        inp = tmp / "rep.bin"
        inp.write_bytes(data)
        comp = tmp / "rep.qtp"
        run_runner("compress", str(inp), str(comp))
        ratio = comp.stat().st_size / len(data)
        assert ratio < 0.5, (
            f"compression ratio {ratio:.2%} on repetitive data, expected < 50%"
        )


# ---------------------------------------------------------------------------
# Difficulty: roundtrip on empty input
# ---------------------------------------------------------------------------

def test_roundtrip_empty() -> None:
    """Empty input must roundtrip to empty output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        inp = tmp / "empty.bin"
        inp.write_bytes(b"")
        comp = tmp / "empty.qtp"
        rest = tmp / "empty.out"
        run_runner("compress", str(inp), str(comp))
        run_runner("decompress", str(comp), str(rest))
        assert rest.read_bytes() == b"", "empty roundtrip failed"


# ---------------------------------------------------------------------------
# Difficulty: verify dictionary entries are actual input substrings
# ---------------------------------------------------------------------------

def test_compressed_dict_contains_input_chunks() -> None:
    """Dictionary entries in the compressed blob must be 5-byte substrings
    that actually appear in the input data."""
    import struct

    data = b"The quick brown fox jumps over the lazy dog. " * 50
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        inp = tmp / "dictcheck.bin"
        inp.write_bytes(data)
        comp = tmp / "dictcheck.qtp"
        run_runner("compress", str(inp), str(comp))
        blob = comp.read_bytes()

    assert len(blob) >= 15, "compressed blob too small"
    magic, version, method, dcb, original_size = struct.unpack_from("<4sBBBQ", blob, 0)
    assert magic == b"QPX1"
    p = 15
    dict_count = int.from_bytes(blob[p:p + dcb], "little")
    p += dcb

    for i in range(dict_count):
        chunk = blob[p + i * 5: p + (i + 1) * 5]
        assert len(chunk) == 5, f"dictionary entry {i} is {len(chunk)} bytes, expected 5"
        assert chunk in data, (
            f"dictionary entry {i} ({chunk!r}) is not a substring of the input"
        )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
