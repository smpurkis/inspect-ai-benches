"""Generated, metamorphic, boundary, and structural LZ77 checks."""

import random
import re
import subprocess
import tempfile
import tomllib
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent
FILES = BASE.parent / "files"
RUNNER = FILES / "run_lz77.sh"
CANDIDATE = FILES / "candidate_kernel.wat"
CONTRACT = tomllib.loads((FILES / "contract.toml").read_text())
MAX_INPUT_BYTES = CONTRACT["codec_limits"]["max_input_bytes"]
COMMAND_TIMEOUT_SECONDS = CONTRACT["codec_limits"]["command_timeout_seconds"]


def canonical_encode(data: bytes) -> bytes:
    output = bytearray()
    literals = bytearray()

    def flush() -> None:
        while literals:
            piece = literals[:128]
            del literals[:128]
            output.append(len(piece) - 1)
            output.extend(piece)

    position = 0
    while position < len(data):
        best_length = best_distance = 0
        for distance in range(1, min(position, 32768) + 1):
            length = 0
            while (length < 130 and position + length < len(data)
                   and data[position - distance + length] == data[position + length]):
                length += 1
            if length > best_length:
                best_length, best_distance = length, distance
        if best_length >= 3:
            flush()
            output.append(0x80 | (best_length - 3))
            output.extend((best_distance - 1).to_bytes(2, "little"))
            position += best_length
        else:
            literals.append(data[position])
            position += 1
            if len(literals) == 128:
                flush()
    flush()
    return bytes(output)


def decode_stream(encoded: bytes) -> bytes:
    output = bytearray()
    position = 0
    while position < len(encoded):
        control = encoded[position]
        position += 1
        if control < 0x80:
            length = control + 1
            end = position + length
            assert end <= len(encoded)
            output.extend(encoded[position:end])
            position = end
            continue
        assert position + 2 <= len(encoded)
        length = (control & 0x7F) + 3
        distance = int.from_bytes(encoded[position:position + 2], "little") + 1
        position += 2
        assert 1 <= distance <= min(len(output), 32768)
        for _ in range(length):
            output.append(output[-distance])
    return bytes(output)


def invoke(mode: str, data: bytes, *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source, output = root / "input", root / "output"
        source.write_bytes(data)
        result = subprocess.run(
            ["bash", str(RUNNER), mode, str(source), str(output)],
            capture_output=True, timeout=COMMAND_TIMEOUT_SECONDS,
        )
        if check:
            assert result.returncode == 0, result.stderr.decode(errors="replace")
            result.stdout = output.read_bytes()
        return result


@pytest.mark.parametrize("seed", [0x1770, 0x1771, 0x1772])
def test_generated_stream_is_canonical(seed: int) -> None:
    rng = random.Random(seed)
    alphabet = rng.randbytes(48)
    data = bytes(alphabet[rng.randrange(len(alphabet))] for _ in range(700))
    data += data[31:170] * 2
    assert invoke("compress", data).stdout == canonical_encode(data)


def test_tie_breaking_and_bounded_history() -> None:
    tie = b"abcXabcYabc"
    assert invoke("compress", tie).stdout == canonical_encode(tie)
    rng = random.Random(0x8000)
    prefix = rng.randbytes(900)
    distant = prefix + prefix[:40]
    assert invoke("compress", distant).stdout == canonical_encode(distant)


def test_metamorphic_append_and_single_byte_mutation() -> None:
    rng = random.Random(0xA77)
    original = bytearray(rng.randbytes(350) + b"match-me" * 30)
    changed = original.copy()
    changed[173] ^= 0x80
    for data in (bytes(original), bytes(changed), bytes(original) + b"tail"):
        encoded = invoke("compress", data).stdout
        assert encoded == canonical_encode(data)
        assert invoke("decompress", encoded).stdout == data


def test_maximum_input_completes_within_contract_and_roundtrips() -> None:
    assert COMMAND_TIMEOUT_SECONDS == 120
    data = random.Random(0x8A11CE).randbytes(MAX_INPUT_BYTES)

    # Incompressible input forces the matcher to advance one byte at a time.
    # invoke() enforces the contract's full command timeout.
    encoded = invoke("compress", data).stdout
    assert decode_stream(encoded) == data


def literal_stream(data: bytes) -> bytes:
    output = bytearray()
    for start in range(0, len(data), 128):
        piece = data[start:start + 128]
        output.append(len(piece) - 1)
        output.extend(piece)
    return bytes(output)


def test_exact_32k_window_boundary() -> None:
    prefix = random.Random(0x8000).randbytes(32769)
    at_limit = literal_stream(prefix[:32768]) + b"\x80\xff\x7f"
    assert invoke("decompress", at_limit).stdout == prefix[:32768] + prefix[:3]
    beyond_limit = literal_stream(prefix) + b"\x80\x00\x80"
    assert invoke("decompress", beyond_limit, check=False).returncode != 0


@pytest.mark.parametrize("stream", [b"\x00", b"\x80", b"\x80\x00", b"\x80\x00\x00"])
def test_validated_decoder_rejects_malformed(stream: bytes) -> None:
    assert invoke("decompress", stream, check=False).returncode != 0


def test_trusted_assembly_and_candidate_reachability() -> None:
    build = (FILES / "build_wasm.sh").read_text()
    suffix = (FILES / "trusted_suffix.wat").read_text()
    source = CANDIDATE.read_text()
    assert "trusted_prefix.wat" in build and "trusted_suffix.wat" in build
    assert "candidate_kernel.wat" in build and "call $find_match" in suffix
    assert len(re.findall(r"\(func\s+\$find_match\b", source)) == 1
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
        assert compiled.read_bytes() == (FILES / "lz77.wasm").read_bytes()
