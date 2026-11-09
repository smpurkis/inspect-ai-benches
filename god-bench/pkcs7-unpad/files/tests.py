import ctypes
import subprocess
from pathlib import Path

FILES = Path("/app/files")


def _library():
    result = subprocess.run(
        ["make", "-C", str(FILES), "all"], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    lib = ctypes.CDLL(str(FILES / "build/libunpad.so"))
    lib.pkcs7_unpad.argtypes = [
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
        ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
    ]
    lib.pkcs7_unpad.restype = ctypes.c_int
    return lib


def _call(data: bytes, block: int, initial: int = 777):
    array = (ctypes.c_uint8 * len(data))(*data)
    output = ctypes.c_size_t(initial)
    result = _library().pkcs7_unpad(array, len(data), block, ctypes.byref(output))
    return result, output.value, bytes(array)


def test_normal_valid_padding():
    assert _call(b"ICE ICE BABY\x04\x04\x04\x04", 16) == (1, 12, b"ICE ICE BABY\x04\x04\x04\x04")


def test_edge_full_block_padding():
    assert _call(bytes([16]) * 16, 16)[:2] == (1, 0)


def test_invariant_failure_preserves_output_and_input():
    data = b"A" * 15 + b"\x00"
    assert _call(data, 16) == (0, 777, data)


def test_determinism_repeated_call():
    data = b"deterministic!" + b"\x02\x02"
    assert _call(data, 16) == _call(data, 16)
