"""Generated, metamorphic, malformed, and structural QuiltPress checks."""

import importlib.util
import random
import re
import struct
import subprocess
import tempfile
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent
FILES = BASE.parent / "files"
RUNNER = FILES / "run_wasm_codec.sh"
CANDIDATE = FILES / "candidate_kernel.wat"


def load_reference():
    spec = importlib.util.spec_from_file_location("hidden_qpx", BASE / "quiltpress_q1_reference.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def invoke(mode: str, data: bytes, *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source, output = root / "input", root / "output"
        source.write_bytes(data)
        result = subprocess.run(
            ["bash", str(RUNNER), mode, str(source), str(output)],
            capture_output=True, timeout=120,
        )
        if check:
            assert result.returncode == 0, result.stderr.decode(errors="replace")
            result.stdout = output.read_bytes()
        return result


@pytest.mark.parametrize("seed", [0x5150, 0x5151, 0x5152])
def test_generated_encoding_matches_independent_reference(seed: int) -> None:
    rng = random.Random(seed)
    chunks = [rng.randbytes(5) for _ in range(8)]
    data = b"".join(chunks[rng.randrange(len(chunks))] for _ in range(330))
    data += rng.randbytes(257)
    expected = load_reference().compress_bytes(data)
    assert invoke("compress", data).stdout == expected


def test_command_boundaries_and_dictionary_ties() -> None:
    ref = load_reference()
    cases = [
        b"abcde" * 255,
        b"abcde" * 256,
        bytes(range(255)) + b"\xff" + bytes(range(255)),
        (b"abcde" + b"vwxyz") * 40,
    ]
    for data in cases:
        assert invoke("compress", data).stdout == ref.compress_bytes(data)


def test_metamorphic_prefix_suffix_and_mutation() -> None:
    ref = load_reference()
    rng = random.Random(0xC0A1)
    original = bytearray(b"token" * 90 + rng.randbytes(80))
    changed = original.copy()
    changed[211] ^= 1
    for data in (bytes(original), b"prefix" + original, bytes(original) + b"suffix", bytes(changed)):
        encoded = invoke("compress", data).stdout
        assert encoded == ref.compress_bytes(data)
        assert invoke("decompress", encoded).stdout == data


@pytest.mark.parametrize("blob", [
    b"", b"NOPE" + b"\x00" * 20,
    struct.pack("<4sBBBQ", b"QPX1", 1, 2, 1, 1) + b"\x00\x00\x00",
    struct.pack("<4sBBBQ", b"QPX1", 1, 2, 1, 5) + b"\x00\x01\x01\x00",
])
def test_trusted_decoder_rejects_malformed(blob: bytes) -> None:
    assert invoke("decompress", blob, check=False).returncode != 0


def test_trusted_assembly_and_candidate_reachability() -> None:
    build = (FILES / "build_wasm.sh").read_text()
    suffix = (FILES / "trusted_suffix.wat").read_text()
    source = CANDIDATE.read_text()
    assert "trusted_prefix.wat" in build and "trusted_suffix.wat" in build
    assert "candidate_kernel.wat" in build and "call $encode_payload" in suffix
    assert len(re.findall(r"\(func\s+\$encode_payload\b", source)) == 1
    forbidden = r"\((?:import|export|memory)\b|\b(?:_start|fd_read|fd_write|proc_exit)\b"
    assert not re.search(forbidden, source)
    assert not CANDIDATE.is_symlink()


def test_declared_output_is_synchronized() -> None:
    subprocess.run(["bash", str(FILES / "build_wasm.sh")], check=True)
    with tempfile.TemporaryDirectory() as directory:
        assembled = Path(directory) / "module.wat"
        compiled = Path(directory) / "module.wasm"
        assembled.write_bytes(b"".join((FILES / name).read_bytes() for name in (
            "trusted_prefix.wat", "candidate_kernel.wat", "trusted_suffix.wat"
        )))
        subprocess.run(["wat2wasm", str(assembled), "-o", str(compiled)], check=True)
        assert compiled.read_bytes() == (FILES / "quiltpress_wasi.wasm").read_bytes()
