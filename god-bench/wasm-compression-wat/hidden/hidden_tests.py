#!/usr/bin/env python3

import hashlib
import random
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


def load_module(name: str, path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_runner(*args: str) -> None:
    cmd = ["bash", str(RUNNER), *args]
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=135,
        )
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            "runner command failed\n"
            f"cmd: {cmd}\n"
            f"returncode: {exc.returncode}\n"
            f"stdout:\n{exc.stdout}\n"
            f"stderr:\n{exc.stderr}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(f"runner command timed out\ncmd: {cmd}") from exc


def run_runner_result(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(RUNNER), *args],
        capture_output=True,
        text=True,
        timeout=135,
    )


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
    ref_path = HIDDEN_DIR / "quiltpress_q1_reference.py"
    ref = load_module("quiltpress_q1_reference", ref_path)

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
    ref_path = HIDDEN_DIR / "quiltpress_q1_reference.py"
    ref = load_module("quiltpress_q1_ref2", ref_path)

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


def test_roundtrip_seeded_generated_inputs() -> None:
    """Cover deterministic incompressible data and command-count boundaries."""
    rng = random.Random(0x51505831)
    block = rng.randbytes(37)
    cases = {
        "incompressible": rng.randbytes(4096),
        "repeated": block * 300,
        "literal_boundary": bytes(range(255)) + b"\xff" + bytes(range(255)),
        "token_boundary": b"abcde" * 256,
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for name, data in cases.items():
            inp = tmp / f"{name}.bin"
            inp.write_bytes(data)
            original, decoded, _ = _roundtrip(inp, tmp)
            assert decoded == original, f"{name} roundtrip failed"


def test_seeded_encoding_is_deterministic() -> None:
    rng = random.Random(0xD37E)
    data = rng.randbytes(1024) + b"deterministic-token" * 300
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        inp = tmp / "deterministic.bin"
        out_a = tmp / "a.qtp"
        out_b = tmp / "b.qtp"
        inp.write_bytes(data)
        run_runner("compress", str(inp), str(out_a))
        run_runner("compress", str(inp), str(out_b))
        assert out_a.read_bytes() == out_b.read_bytes()


def test_generated_wasm_output_is_reference_compatible() -> None:
    ref_path = HIDDEN_DIR / "quiltpress_q1_reference.py"
    ref = load_module("quiltpress_generated_ref", ref_path)

    rng = random.Random(0xC0DEC)
    data = rng.randbytes(2048) + b"cross-codec-block" * 200
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        inp = tmp / "generated.bin"
        compressed = tmp / "generated.qtp"
        inp.write_bytes(data)
        run_runner("compress", str(inp), str(compressed))
        assert ref.decompress_bytes(compressed.read_bytes()) == data


def test_rejects_malformed_qpx1_streams() -> None:
    header = struct.pack("<4sBBBQ", b"QPX1", 1, 2, 1, 1)
    malformed = {
        "bad_magic": b"NOPE" + header[4:] + b"\x00",
        "bad_version": header[:4] + b"\x02" + header[5:] + b"\x00",
        "bad_method": header[:5] + b"\x03" + header[6:] + b"\x00",
        "bad_width": header[:6] + b"\x00" + header[7:] + b"\x00",
        "truncated_literal": header + b"\x00\x00\x02A",
        "zero_literal": header + b"\x00\x00\x00",
        "unknown_command": header + b"\x00\xff\x01A",
        "invalid_token": header + b"\x00\x01\x01\x00",
        "size_mismatch": header + b"\x00",
        "truncated_dictionary": header + b"\x01abcd",
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for name, blob in malformed.items():
            inp = tmp / f"{name}.qtp"
            out = tmp / f"{name}.out"
            inp.write_bytes(blob)
            result = run_runner_result("decompress", str(inp), str(out))
            assert result.returncode != 0, f"accepted malformed case {name}"


def test_reference_oracle_known_vector_and_candidate_decoder() -> None:
    ref = load_module(
        "quiltpress_known_vector", HIDDEN_DIR / "quiltpress_q1_reference.py"
    )
    blob = (
        struct.pack("<4sBBBQ", b"QPX1", 1, 2, 1, 5)
        + b"\x01"
        + b"abcde"
        + b"\x01\x01\x00"
    )
    assert ref.decompress_bytes(blob) == b"abcde"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        encoded = tmp / "known.qpx"
        output = tmp / "known.out"
        encoded.write_bytes(blob)
        run_runner("decompress", str(encoded), str(output))
        assert output.read_bytes() == b"abcde"


def test_visible_and_hidden_format_references_agree() -> None:
    visible = load_module(
        "quiltpress_visible", BASE.parent / "files" / "quiltpress_q1.py"
    )
    hidden = load_module(
        "quiltpress_hidden", HIDDEN_DIR / "quiltpress_q1_reference.py"
    )
    rng = random.Random(0xA61EE)
    data = rng.randbytes(513) + b"abcde" * 100
    visible_blob = visible.compress_bytes(data)
    hidden_blob = hidden.compress_bytes(data)
    assert visible_blob == hidden_blob
    assert visible.decompress_bytes(hidden_blob) == data
    assert hidden.decompress_bytes(visible_blob) == data


def test_resource_limits_and_sandboxed_preopens() -> None:
    huge_header = struct.pack("<4sBBBQ", b"QPX1", 1, 2, 1, 64 * 1024 * 1024 + 1)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        encoded = tmp / "huge.qpx"
        output = tmp / "output"
        encoded.write_bytes(huge_header + b"\x00")
        result = run_runner_result("decompress", str(encoded), str(output))
        assert result.returncode != 0, "accepted oversized declared output"

        oversized = tmp / "oversized.bin"
        with oversized.open("wb") as stream:
            stream.truncate(32 * 1024 * 1024 + 1)
        result = run_runner_result("compress", str(oversized), str(output))
        assert result.returncode != 0, "accepted oversized compression input"

    runner = RUNNER.read_text()
    assert "--dir / --" not in runner
    assert "::/input" in runner and "::/output" in runner


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
