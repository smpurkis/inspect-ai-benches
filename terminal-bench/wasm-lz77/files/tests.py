"""Visible tests for wasm-lz77: LZ77 compression implemented in WAT/WASM.

The agent must produce:
  /app/files/lz77.wat   — WAT source
  /app/files/lz77.wasm  — compiled with wat2wasm
  /app/files/run_lz77.sh is provided (do not modify)

Usage:
  bash /app/files/run_lz77.sh compress   <input>  <output>
  bash /app/files/run_lz77.sh decompress <input>  <output>
"""

import os
import subprocess
import tempfile
import pytest

FILES = "/app/files"
RUNNER = os.path.join(FILES, "run_lz77.sh")
WAT = os.path.join(FILES, "lz77.wat")
WASM = os.path.join(FILES, "lz77.wasm")
CORPUS = os.path.join(FILES, "corpus")


def compress(src: str, dst: str, *, timeout=30):
    r = subprocess.run(["bash", RUNNER, "compress", src, dst],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def decompress(src: str, dst: str, *, timeout=30):
    r = subprocess.run(["bash", RUNNER, "decompress", src, dst],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def roundtrip(data: bytes, *, timeout=30) -> bytes:
    """Compress then decompress data; return decompressed bytes."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        orig = f.name
    compressed = orig + ".lz77"
    restored = orig + ".out"
    try:
        rc, out, err = compress(orig, compressed, timeout=timeout)
        assert rc == 0, f"compress failed (rc={rc}):\n{err}"
        assert os.path.isfile(compressed), "compress produced no output file"

        rc, out, err = decompress(compressed, restored, timeout=timeout)
        assert rc == 0, f"decompress failed (rc={rc}):\n{err}"
        assert os.path.isfile(restored), "decompress produced no output file"

        return open(restored, "rb").read()
    finally:
        for p in (orig, compressed, restored):
            if os.path.exists(p):
                os.unlink(p)


# ---------------------------------------------------------------------------
# Artifact checks
# ---------------------------------------------------------------------------

def test_wat_exists():
    assert os.path.isfile(WAT), f"{WAT} not found"


def test_wasm_exists():
    assert os.path.isfile(WASM), f"{WASM} not found"


def test_runner_exists():
    assert os.path.isfile(RUNNER), "run_lz77.sh not found"
    assert os.access(RUNNER, os.X_OK), "run_lz77.sh not executable"


def test_wasm_compiles_from_wat():
    """WAT source can be compiled by wat2wasm."""
    with tempfile.NamedTemporaryFile(suffix=".wasm", delete=False) as f:
        tmp_wasm = f.name
    try:
        r = subprocess.run(["wat2wasm", WAT, "-o", tmp_wasm], capture_output=True, text=True)
        assert r.returncode == 0, f"wat2wasm failed:\n{r.stderr}"
        assert os.path.getsize(tmp_wasm) > 0
    finally:
        if os.path.exists(tmp_wasm):
            os.unlink(tmp_wasm)


# ---------------------------------------------------------------------------
# Roundtrip correctness
# ---------------------------------------------------------------------------

def test_roundtrip_hello():
    data = b"Hello, World!"
    result = roundtrip(data)
    assert result == data, f"roundtrip mismatch: {result!r} != {data!r}"


def test_roundtrip_empty():
    data = b""
    result = roundtrip(data)
    assert result == data


def test_roundtrip_single_byte():
    data = b"X"
    result = roundtrip(data)
    assert result == data


def test_roundtrip_binary():
    """Roundtrip arbitrary binary data including all byte values."""
    data = bytes(range(256))
    result = roundtrip(data)
    assert result == data, "roundtrip failed on byte range 0-255"


def test_roundtrip_repetitive():
    """Highly repetitive data must roundtrip correctly."""
    data = b"abcabcabc" * 100
    result = roundtrip(data)
    assert result == data


def test_roundtrip_from_corpus_repetitive():
    path = os.path.join(CORPUS, "repetitive.txt")
    if not os.path.isfile(path):
        pytest.skip("corpus/repetitive.txt not found")
    data = open(path, "rb").read()
    result = roundtrip(data)
    assert result == data


def test_roundtrip_from_corpus_english():
    path = os.path.join(CORPUS, "english.txt")
    if not os.path.isfile(path):
        pytest.skip("corpus/english.txt not found")
    data = open(path, "rb").read()
    result = roundtrip(data)
    assert result == data


def test_roundtrip_test_txt():
    """Roundtrip the provided test.txt corpus file."""
    path = os.path.join(FILES, "test.txt")
    if not os.path.isfile(path):
        pytest.skip("test.txt not found")
    data = open(path, "rb").read()
    result = roundtrip(data)
    assert result == data, f"test.txt roundtrip failed: {len(result)} bytes vs {len(data)} expected"


# ---------------------------------------------------------------------------
# Compression ratio
# ---------------------------------------------------------------------------

def compression_ratio(data: bytes) -> float:
    """Return ratio = compressed_size / original_size (lower is better)."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        orig = f.name
    compressed = orig + ".lz77"
    try:
        rc, _, err = compress(orig, compressed)
        assert rc == 0, f"compress failed: {err}"
        return os.path.getsize(compressed) / len(data)
    finally:
        for p in (orig, compressed):
            if os.path.exists(p):
                os.unlink(p)


def test_compression_ratio_repetitive():
    """Highly repetitive data should compress to < 50% of original size."""
    data = b"abcdefgh" * 1000  # 8000 bytes
    ratio = compression_ratio(data)
    assert ratio < 0.5, f"compression ratio {ratio:.2%} not < 50% on repetitive data"


def test_compression_ratio_corpus():
    """The provided corpus files should compress to < 50%."""
    path = os.path.join(FILES, "test.txt")
    if not os.path.isfile(path):
        pytest.skip("test.txt not found")
    data = open(path, "rb").read()
    ratio = compression_ratio(data)
    assert ratio < 0.5, f"corpus test.txt ratio {ratio:.2%} not < 50%"
