"""Hidden tests for wasm-lz77: additional roundtrip and compression ratio tests."""

import os
import subprocess
import tempfile
import hashlib
import pytest

FILES = "/app/files"
RUNNER = os.path.join(FILES, "run_lz77.sh")
WASM = os.path.join(FILES, "lz77.wasm")
CORPUS = os.path.join(FILES, "corpus")


def compress(src: str, dst: str, *, timeout=60):
    r = subprocess.run(["bash", RUNNER, "compress", src, dst],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stderr


def decompress(src: str, dst: str, *, timeout=60):
    r = subprocess.run(["bash", RUNNER, "decompress", src, dst],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stderr


def roundtrip(data: bytes, *, timeout=60) -> bytes:
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        orig = f.name
    compressed = orig + ".lz77"
    restored = orig + ".out"
    try:
        rc, err = compress(orig, compressed, timeout=timeout)
        assert rc == 0, f"compress failed (rc={rc}):\n{err}"
        rc, err = decompress(compressed, restored, timeout=timeout)
        assert rc == 0, f"decompress failed (rc={rc}):\n{err}"
        return open(restored, "rb").read()
    finally:
        for p in (orig, compressed, restored):
            if os.path.exists(p):
                os.unlink(p)


def get_ratio(data: bytes, *, timeout=60) -> float:
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        orig = f.name
    compressed = orig + ".lz77"
    try:
        rc, err = compress(orig, compressed, timeout=timeout)
        assert rc == 0, f"compress failed: {err}"
        return os.path.getsize(compressed) / len(data)
    finally:
        for p in (orig, compressed):
            if os.path.exists(p):
                os.unlink(p)


# ---------------------------------------------------------------------------
# Correctness: roundtrip on varied data
# ---------------------------------------------------------------------------

def test_roundtrip_null_bytes():
    data = b"\x00" * 500
    assert roundtrip(data) == data


def test_roundtrip_random_like():
    """Data with low entropy (structured but not trivially repetitive)."""
    import struct
    data = b""
    for i in range(1000):
        data += struct.pack("<I", i * 6364136223846793005 & 0xFFFFFFFF)
    result = roundtrip(data)
    assert result == data, f"roundtrip length mismatch: {len(result)} vs {len(data)}"


def test_roundtrip_large_repetitive():
    """Large repetitive data (32KB) roundtrips correctly."""
    data = (b"the quick brown fox jumps over the lazy dog\n") * 750
    result = roundtrip(data, timeout=120)
    assert result == data


def test_roundtrip_test_full_txt():
    path = os.path.join(FILES, "test_full.txt")
    if not os.path.isfile(path):
        pytest.skip("test_full.txt not present")
    data = open(path, "rb").read()
    # Use md5 to compare (faster than byte comparison on large data)
    result = roundtrip(data, timeout=300)
    assert hashlib.md5(result).hexdigest() == hashlib.md5(data).hexdigest(), \
        f"test_full.txt roundtrip failed: {len(result)} vs {len(data)} bytes"


def test_roundtrip_corpus_code():
    path = os.path.join(CORPUS, "code.py")
    if not os.path.isfile(path):
        pytest.skip("corpus/code.py not present")
    data = open(path, "rb").read()
    result = roundtrip(data)
    assert result == data


def test_roundtrip_single_byte_repeated():
    path = os.path.join(CORPUS, "single_byte.bin")
    if not os.path.isfile(path):
        data = b"A" * 10000
    else:
        data = open(path, "rb").read()
    result = roundtrip(data)
    assert result == data


# ---------------------------------------------------------------------------
# Compression ratio requirements
# ---------------------------------------------------------------------------

def test_ratio_corpus_english():
    path = os.path.join(CORPUS, "english.txt")
    if not os.path.isfile(path):
        pytest.skip("corpus/english.txt not present")
    data = open(path, "rb").read()
    ratio = get_ratio(data)
    assert ratio < 0.5, f"english.txt compression ratio {ratio:.2%} >= 50%"


def test_ratio_single_byte():
    """10KB of single repeated byte should compress to near 0%."""
    data = b"Z" * 10000
    ratio = get_ratio(data)
    assert ratio < 0.1, f"single-byte ratio {ratio:.2%} is surprisingly high (expected < 10%)"


# ---------------------------------------------------------------------------
# WAT source is genuine (not pre-compiled from another language)
# ---------------------------------------------------------------------------

def test_wat_is_text():
    """lz77.wat must be a text file (not binary)."""
    wat_path = os.path.join(FILES, "lz77.wat")
    if not os.path.isfile(wat_path):
        pytest.skip("lz77.wat not found")
    data = open(wat_path, "rb").read(200)
    # WAT files start with (module or whitespace + (module
    text = data.decode("utf-8", errors="replace")
    assert "module" in text, "lz77.wat does not look like a WAT module"
    # Should not be a binary WASM file
    assert not data.startswith(b"\x00asm"), "lz77.wat appears to be a binary WASM file"


def test_wat_uses_standard_instructions():
    """lz77.wat must be valid WAT (recompile to verify)."""
    wat_path = os.path.join(FILES, "lz77.wat")
    if not os.path.isfile(wat_path):
        pytest.skip("lz77.wat not found")
    with tempfile.NamedTemporaryFile(suffix=".wasm", delete=False) as f:
        tmp = f.name
    try:
        r = subprocess.run(["wat2wasm", wat_path, "-o", tmp],
                           capture_output=True, text=True)
        assert r.returncode == 0, f"wat2wasm rejected lz77.wat:\n{r.stderr}"
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
