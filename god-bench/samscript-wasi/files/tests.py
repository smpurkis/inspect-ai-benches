import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
COMPILER = ROOT / "compiler.py"


def compile_and_run(source):
    with tempfile.TemporaryDirectory() as tmp:
        sam, wasm = Path(tmp) / "case.sam", Path(tmp) / "case.wasm"
        sam.write_text(source)
        built = subprocess.run([sys.executable, str(COMPILER), "compile", str(sam), "-o", str(wasm),
                                "--target", "wasm32-wasi"], capture_output=True, text=True)
        assert built.returncode == 0, built.stderr
        result = subprocess.run(["wasmtime", str(wasm)], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        return result.stdout, wasm.read_bytes()


def test_normal_nested_loops():
    source = """fn main() { let i = 0; let score = 0; loop { i += 1; let j = 0; loop { j += 1; if j == 2 { break; } score += i; } if i == 4 { break; } } return score; }"""
    assert compile_and_run(source)[0] == "10\n"


def test_edge_short_circuit_skips_trap():
    source = """fn main() { if false && (1 % 0 == 0) { return 90; } if true || (1 % 0 == 0) { return 7; } return 8; }"""
    assert compile_and_run(source)[0] == "7\n"


def test_invariant_return_escapes_nested_control():
    source = """fn pick(n) { loop { if n > 3 { loop { return n * 2; } } return 1; } } fn main() { return pick(8); }"""
    assert compile_and_run(source)[0] == "16\n"


def test_deterministic_rerun():
    source = """fn main() { let n = 6; let x = 1; loop { if n == 0 { break; } x *= n; n -= 1; } return x; }"""
    first = compile_and_run(source)
    second = compile_and_run(source)
    assert first[0] == second[0] == "720\n"
    assert hashlib.sha256(first[1]).digest() == hashlib.sha256(second[1]).digest()
