import ctypes
import hashlib
import os
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FILES = Path("/app/files")
BUILD = Path("/tmp/pkcs7-verifier")
ALLOWED = {
    "Makefile", "TASK.md", "contract.toml", "instructions.md", "tests.py",
    "src/cli.c", "src/unpad.c", "src/unpad.h",
}
TRUSTED_HASHES = {
    "Makefile": "4e3d6ebf4f0664c275396605f6abb01180d8743c82577b7c1637df90b0896c5d",
    "TASK.md": "18f00dc66253d548db0d59fbb66af5dad4a25c2411f00e6a1f522b750102ff80",
    "contract.toml": "60575d80fcfa325f634a4c56a858888fba84401e97d7a480e7531537a00ba71d",
    "instructions.md": "655928a1994dd8733f5e5720b9e033f16b80487eeddc28194a98bee04e31f513",
    "tests.py": "163c0ceb14fd3143773e9b41f6474e61df0aa7ddb72e870a9bc2c0377c08b976",
    "src/cli.c": "1d02e89524cb334621af1ac05f08314f25f7e87a11145108fe36db3183639667",
    "src/unpad.h": "71d56995a359dd3a71dfc9035cbd18e805719ab20e88a77ab91b87a30591072f",
}


def _stage():
    if BUILD.exists():
        shutil.rmtree(BUILD)
    (BUILD / "src").mkdir(parents=True)
    for relative in ALLOWED:
        source = FILES / relative
        assert source.is_file() and not source.is_symlink(), f"missing/symlink: {relative}"
        target = BUILD / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    actual = {
        str(path.relative_to(FILES))
        for path in FILES.rglob("*")
        if path.is_file() and "build" not in path.parts and "__pycache__" not in path.parts
    }
    assert actual == ALLOWED, f"undeclared files: {sorted(actual ^ ALLOWED)}"
    result = subprocess.run(
        ["make", "-C", str(BUILD), "clean", "all"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr[-3000:]


def _lib():
    _stage()
    lib = ctypes.CDLL(str(BUILD / "build/libunpad.so"))
    lib.pkcs7_unpad.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
                                ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    lib.pkcs7_unpad.restype = ctypes.c_int
    return lib


def _call(lib, data, block, initial=0xD00DFEED):
    array = (ctypes.c_uint8 * len(data))(*data)
    out = ctypes.c_size_t(initial)
    status = lib.pkcs7_unpad(array, len(data), block, ctypes.byref(out))
    return status, out.value, bytes(array)


def test_protected_scaffold_and_candidate_reachability():
    _stage()
    source = (BUILD / "src/unpad.c").read_text()
    assert re.search(r"\bpkcs7_unpad\s*\(", source)
    forbidden = r"\b(asm|__asm__|pthread_|signal|raise|clock|gettimeofday|memchr|memcmp)\b"
    assert not re.search(forbidden, source)
    cli = (BUILD / "src/cli.c").read_text()
    assert len(re.findall(r"\bpkcs7_unpad\s*\(", cli)) == 1
    for relative, expected in TRUSTED_HASHES.items():
        assert hashlib.sha256((FILES / relative).read_bytes()).hexdigest() == expected
        assert hashlib.sha256((BUILD / relative).read_bytes()).hexdigest() == expected


def test_all_padding_lengths_and_every_invalid_position():
    lib = _lib()
    rng = random.Random(0x7A11)
    for block in list(range(1, 33)) + [63, 127, 255]:
        prefix = bytes(rng.randrange(256) for _ in range(block))
        for pad in range(1, block + 1):
            data = prefix + bytes([pad]) * pad
            remainder = len(data) % block
            if remainder:
                data = bytes(block - remainder) + data
            assert _call(lib, data, block)[:2] == (1, len(data) - pad)
            for offset in range(pad):
                broken = bytearray(data)
                broken[len(data) - pad + offset] ^= 0x80
                if offset == pad - 1 and broken[-1] in range(1, block + 1):
                    broken[-1] = 0
                status, output, unchanged = _call(lib, bytes(broken), block)
                assert (status, output, unchanged) == (0, 0xD00DFEED, bytes(broken))


def test_generated_oracle_boundaries_and_failure_atomicity():
    lib = _lib()
    rng = random.Random(20260726)
    for _ in range(500):
        block = rng.randint(1, 255)
        length = block * rng.randint(1, 5)
        data = bytearray(rng.randbytes(length))
        expected = False
        p = data[-1]
        if 1 <= p <= block and all(value == p for value in data[-p:]):
            expected = True
        status, output, unchanged = _call(lib, bytes(data), block)
        assert status == int(expected)
        assert output == (length - p if expected else 0xD00DFEED)
        assert unchanged == bytes(data)
    one = (ctypes.c_uint8 * 1)(1)
    out = ctypes.c_size_t(91)
    for length, block in [(0, 16), (1, 0), (1, 256), (15, 16), (17, 16)]:
        assert lib.pkcs7_unpad(one, length, block, ctypes.byref(out)) == 0
        assert out.value == 91
    size_max = ctypes.c_size_t(-1).value
    assert lib.pkcs7_unpad(one, size_max, 16, ctypes.byref(out)) == 0
    assert lib.pkcs7_unpad(None, 16, 16, ctypes.byref(out)) == 0
    assert lib.pkcs7_unpad(None, size_max, 255, ctypes.byref(out)) == 0
    assert lib.pkcs7_unpad(one, 1, 1, None) == 0


def _symbol_range(binary):
    output = subprocess.check_output(["nm", "-S", "--defined-only", str(binary)], text=True)
    match = re.search(r"^([0-9a-f]+)\s+([0-9a-f]+)\s+T\s+pkcs7_unpad$", output, re.M)
    assert match
    return int(match.group(1), 16), int(match.group(2), 16)


def _trace(binary, block, pad, bad):
    log = BUILD / f"lackey-{block}-{pad}-{bad}.log"
    subprocess.run(
        ["valgrind", "--quiet", "--tool=lackey", "--trace-mem=yes",
         f"--log-file={log}", str(binary), str(block), str(pad), str(bad)],
        check=True, timeout=30,
    )
    start, size = _symbol_range(binary)
    trace = []
    in_candidate = False
    for line in log.read_text().splitlines():
        match = re.match(r"\s*([IL])\s+([0-9A-Fa-f]+),([0-9]+)", line)
        if not match:
            continue
        address = int(match.group(2), 16)
        if match.group(1) == "I":
            in_candidate = start <= address < start + size
            if in_candidate:
                trace.append(("I", address - start, int(match.group(3))))
        elif in_candidate:
            trace.append(("L", address, int(match.group(3))))
    assert trace and any(event[0] == "L" for event in trace)
    # argv byte length shifts Valgrind's synthetic stack base between runs.
    # Relative addresses retain the exact candidate load pattern.
    first_load = next(event[1] for event in trace if event[0] == "L")
    return [
        (kind, address - first_load if kind == "L" else address, width)
        for kind, address, width in trace
    ]


def test_equal_branch_and_load_traces_for_equal_lengths():
    _stage()
    binary = BUILD / "trace-driver"
    result = subprocess.run(
        ["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-fno-pie", "-no-pie",
         "-I", str(BUILD / "src"), str(BUILD / "src/unpad.c"),
         "/app/hidden/trace_driver.c", "-o", str(binary)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    disassembly = subprocess.check_output(["objdump", "-d", str(binary)], text=True)
    body = disassembly.split("<pkcs7_unpad>:", 1)[1].split("\n\n", 1)[0]
    assert not re.search(r"\bcallq?\b", body), "candidate may not move traced work into helpers"
    for block in (8, 16, 31, 255):
        baseline = _trace(binary, block, block, block)
        for pad in range(block + 2):
            assert _trace(binary, block, pad, block) == baseline
        for bad in range(block):
            assert _trace(binary, block, block, bad) == baseline


def test_metamorphic_prefix_independence_and_repeatability():
    lib = _lib()
    rng = random.Random(911)
    for block in (8, 16, 32):
        pad = block // 2
        suffix = bytes([pad]) * pad
        first = rng.randbytes(block * 2 - pad) + suffix
        second = rng.randbytes(block * 2 - pad) + suffix
        assert _call(lib, first, block)[:2] == _call(lib, second, block)[:2] == (1, block * 2 - pad)
        assert _call(lib, first, block) == _call(lib, first, block)
