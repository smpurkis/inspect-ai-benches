#!/usr/bin/env python3

import hashlib
import importlib.util
import struct
import tempfile
from pathlib import Path


BASE = Path(__file__).resolve().parent
REFERENCE_FILE = BASE / "quiltpress_q1_reference.py"
STUDENT_FILE = Path("/app/step_1/files/quiltpress_q1.py")
TEST_FULL = BASE / "test_full.txt"
TEST_PDF = BASE / "test.pdf"

TEST_FULL_SHA256 = "7b57ff0334e57b1f3e62ddc59e03cdcad7efe7c22a61fcc79975b9b4b0b4e1be"
TEST_PDF_SHA256 = "d937cf6c07c7540387e74e369b1c776098da0b6e260f421035c852534ec82ccd"

# Use 10× smaller slices for codec tests — full files (903KB / 1.1MB) caused
# O(n²) student codecs to hang pytest for 20+ minutes.
TEXT_SAMPLE = 90_000   # ~90 KB of test_full.txt
PDF_SAMPLE  = 110_000  # ~110 KB of test.pdf


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REFERENCE = _load_module("quiltpress_q1_reference", REFERENCE_FILE)
STUDENT = _load_module("quiltpress_q1_student", STUDENT_FILE)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_blob(codec, blob: bytes) -> tuple[int, int, bytes, bytes]:
    magic, version, method, dict_count_bytes, original_size = struct.unpack_from(
        codec.HEADER_FMT, blob, 0
    )
    assert magic == codec.MAGIC
    assert version == codec.VERSION
    assert method == codec.METHOD_CUSTOM
    assert original_size > 0

    p = codec.HEADER_SIZE
    dict_count = int.from_bytes(blob[p : p + dict_count_bytes], "little")
    p += dict_count_bytes
    dict_size = dict_count * codec.CHUNK_LEN
    dictionary_bytes = blob[p : p + dict_size]
    payload = blob[p + dict_size :]
    return dict_count_bytes, dict_count, dictionary_bytes, payload


def test_hidden_fixture_hashes() -> None:
    assert sha256_bytes(TEST_FULL.read_bytes()) == TEST_FULL_SHA256
    assert sha256_bytes(TEST_PDF.read_bytes()) == TEST_PDF_SHA256


def test_hidden_roundtrip_text() -> None:
    """Student codec must roundtrip a sample of test_full.txt and compress it."""
    original = TEST_FULL.read_bytes()[:TEXT_SAMPLE]
    blob = STUDENT.compress_bytes(original)
    restored = STUDENT.decompress_bytes(blob)
    assert restored == original, "text roundtrip mismatch"
    assert len(blob) < len(original), (
        f"text compressed size {len(blob)} >= original {len(original)}"
    )


def test_hidden_roundtrip_pdf() -> None:
    """Student codec must roundtrip a sample of test.pdf and compress it."""
    original = TEST_PDF.read_bytes()[:PDF_SAMPLE]
    blob = STUDENT.compress_bytes(original)
    restored = STUDENT.decompress_bytes(blob)
    assert restored == original, "pdf roundtrip mismatch"
    assert len(blob) < len(original), (
        f"pdf compressed size {len(blob)} >= original {len(original)}"
    )


def test_hidden_cross_codec_compress_student_decompress_reference() -> None:
    """Compress with student codec, decompress with reference.
    Proves the student's output is format-compatible."""
    for path, size in ((TEST_FULL, TEXT_SAMPLE), (TEST_PDF, PDF_SAMPLE)):
        original = path.read_bytes()[:size]
        blob = STUDENT.compress_bytes(original)
        restored = REFERENCE.decompress_bytes(blob)
        assert restored == original, (
            f"cross-codec failed: student compress → reference decompress "
            f"on {path.name}"
        )


def test_hidden_cross_codec_compress_reference_decompress_student() -> None:
    """Compress with reference codec, decompress with student.
    Proves the student's decompressor handles valid format correctly."""
    for path, size in ((TEST_FULL, TEXT_SAMPLE), (TEST_PDF, PDF_SAMPLE)):
        original = path.read_bytes()[:size]
        blob = REFERENCE.compress_bytes(original)
        restored = STUDENT.decompress_bytes(blob)
        assert restored == original, (
            f"cross-codec failed: reference compress → student decompress "
            f"on {path.name}"
        )


def test_hidden_dictionary_contains_common_sequence() -> None:
    """Student codec dictionary for English text should contain b' the '."""
    blob = STUDENT.compress_bytes(TEST_FULL.read_bytes()[:TEXT_SAMPLE])
    _, dict_count, dictionary_bytes, _ = parse_blob(STUDENT, blob)
    assert dict_count > 0, "dictionary is empty"

    dictionary = [
        dictionary_bytes[i : i + STUDENT.CHUNK_LEN]
        for i in range(0, len(dictionary_bytes), STUDENT.CHUNK_LEN)
    ]
    assert b" the " in dictionary, (
        f"expected b' the ' in dictionary of {dict_count} entries"
    )


def test_hidden_edge_cases_student_codec() -> None:
    """Student codec must handle edge-case inputs correctly."""
    cases = [b"", b"a", b"aaaaa", b"abcdeabcdeabcde", bytes(range(256))]
    for data in cases:
        blob = STUDENT.compress_bytes(data)
        restored = STUDENT.decompress_bytes(blob)
        assert restored == data, (
            f"roundtrip failed for {len(data)}-byte input"
        )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
