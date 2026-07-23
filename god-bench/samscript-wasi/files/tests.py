import re
import subprocess
import sys
from pathlib import Path

COMPILER = Path("/app/files/compiler.py")
SAMPLES = Path("/app/files/samples")


def _find_compiler() -> list[str]:
    """Return the single contract-authorized compiler entry point."""
    assert COMPILER.is_file(), f"Compiler not found at {COMPILER}"
    return [sys.executable, str(COMPILER)]


def _compile_to_wasm(sam_file: Path, out_wasm: str, timeout: int = 120) -> subprocess.CompletedProcess:
    compiler = _find_compiler()
    return subprocess.run(
        [*compiler, "compile", str(sam_file), "-o", out_wasm, "--target", "wasm32-wasi"],
        capture_output=True, text=True, timeout=timeout,
    )


def _run_wasm(wasm_file: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["wasmtime", wasm_file],
        capture_output=True, text=True, timeout=timeout,
    )


def _assert_real_wasm(wasm_file: str, *, min_reachable: int = 3) -> None:
    """Verify that _start transitively calls real compiled functions.

    The compiled WASM must contain real arithmetic and control-flow instructions
    reachable from _start — not just embedded output strings.
    """
    # 1. Count function imports to distinguish imports from user functions
    xdump = subprocess.run(
        ["wasm-objdump", "-x", wasm_file],
        capture_output=True, text=True, timeout=30,
    )
    assert xdump.returncode == 0, f"wasm-objdump -x failed: {xdump.stderr}"

    import_count = 0
    in_imports = False
    for line in xdump.stdout.splitlines():
        if re.match(r'^Import\[', line):
            in_imports = True
            continue
        if in_imports:
            if '- func[' in line:
                import_count += 1
            elif line and not line[0].isspace():
                in_imports = False

    # 2. Disassemble and split into per-function bodies
    ddump = subprocess.run(
        ["wasm-objdump", "-d", wasm_file],
        capture_output=True, text=True, timeout=30,
    )
    assert ddump.returncode == 0, f"wasm-objdump -d failed: {ddump.stderr}"

    func_hdr_re = re.compile(r'^[0-9a-f]+\s+func\[(\d+)\](?:\s+<([^>]+)>)?:')
    call_re = re.compile(r'\bcall\s+(\d+)\b')

    func_bodies = {}  # idx -> {"name": str, "text": str}
    cur_idx = None
    cur_lines = []

    for line in ddump.stdout.splitlines():
        m = func_hdr_re.match(line)
        if m:
            if cur_idx is not None:
                func_bodies[cur_idx]["text"] = "\n".join(cur_lines)
            cur_idx = int(m.group(1))
            func_bodies[cur_idx] = {"name": m.group(2) or "", "text": ""}
            cur_lines = []
        elif cur_idx is not None:
            cur_lines.append(line.lower())
    if cur_idx is not None:
        func_bodies[cur_idx]["text"] = "\n".join(cur_lines)

    # 3. Find _start
    start_idx = None
    for idx, info in func_bodies.items():
        if info["name"] == "_start":
            start_idx = idx
            break
    assert start_idx is not None, "No _start function found in WASM binary"

    # 4. BFS: find all user functions reachable from _start
    reachable = set()
    queue = [start_idx]
    while queue:
        cur = queue.pop(0)
        if cur in reachable:
            continue
        reachable.add(cur)
        body = func_bodies.get(cur, {}).get("text", "")
        for m in call_re.finditer(body):
            target = int(m.group(1))
            if target >= import_count and target not in reachable:
                queue.append(target)

    reachable_user = reachable - {start_idx}

    # 5. Collect code from all reachable functions (including _start)
    reachable_code = "\n".join(
        func_bodies[idx]["text"] for idx in reachable if idx in func_bodies
    )

    f64_ops = [
        "f64.add", "f64.sub", "f64.mul", "f64.div",
        "f64.lt", "f64.gt", "f64.eq", "f64.ge", "f64.le", "f64.ne",
    ]
    cf_ops = ["loop", "br_if", "block"]

    found_f64 = [op for op in f64_ops if op in reachable_code]
    found_cf = [op for op in cf_ops if op in reachable_code]

    # Must have f64 arithmetic in reachable code
    assert len(found_f64) >= 2, (
        f"Code reachable from _start has no f64 arithmetic instructions "
        f"(found: {found_f64}). Reachable user functions: {len(reachable_user)}. "
        f"Programs with arithmetic must compile to actual WASM numeric instructions."
    )

    # Must have control flow in reachable code
    assert len(found_cf) >= 1, (
        f"Code reachable from _start has no control flow instructions "
        f"(found: {found_cf}). Reachable user functions: {len(reachable_user)}. "
        f"Programs with loops/conditionals must compile to actual WASM control flow."
    )

    # Must have enough reachable user functions, OR a large _start (inlined compiler)
    start_text = func_bodies.get(start_idx, {}).get("text", "")
    start_instr_count = sum(1 for l in start_text.splitlines() if '|' in l)

    assert len(reachable_user) >= min_reachable or start_instr_count > 100, (
        f"Only {len(reachable_user)} user functions reachable from _start "
        f"(expected >= {min_reachable}), and _start has only {start_instr_count} "
        f"instructions. A program with multiple user-defined functions must "
        f"compile to real WASM functions called from _start — not dead code "
        f"that exists only to pad the binary."
    )


def test_compiler_exists():
    """A samscript compiler binary exists and is executable."""
    compiler = _find_compiler()
    assert Path(compiler[-1]).exists(), f"Compiler not found at {compiler[-1]}"


def test_compile_hello_to_wasm():
    """Compiling hello.sam produces a non-empty .wasm file."""
    result = _compile_to_wasm(SAMPLES / "hello.sam", "/tmp/test_hello.wasm")
    assert result.returncode == 0, f"Compilation failed:\n{result.stderr}"
    wasm = Path("/tmp/test_hello.wasm")
    assert wasm.exists(), "Output .wasm file not created"
    assert wasm.stat().st_size > 0, "Output .wasm file is empty"
    # Check it starts with the wasm magic bytes
    magic = wasm.read_bytes()[:4]
    assert magic == b'\x00asm', f"File does not start with wasm magic bytes, got {magic!r}"


def test_hello_wasm_output():
    """Running compiled hello.sam produces 'hello world'."""
    comp = _compile_to_wasm(SAMPLES / "hello.sam", "/tmp/test_hello_run.wasm")
    assert comp.returncode == 0, f"Compilation failed:\n{comp.stderr}"
    result = _run_wasm("/tmp/test_hello_run.wasm")
    assert result.returncode == 0, f"wasmtime execution failed:\n{result.stderr}"
    assert result.stdout.strip() == "hello world", (
        f"Expected 'hello world', got: {result.stdout!r}"
    )


def test_compile_arithmetic_to_wasm():
    """Compiling arithmetic.sam produces a valid .wasm file that runs correctly."""
    comp = _compile_to_wasm(SAMPLES / "arithmetic.sam", "/tmp/test_arith.wasm")
    assert comp.returncode == 0, f"Compilation failed:\n{comp.stderr}"
    _assert_real_wasm("/tmp/test_arith.wasm", min_reachable=1)

    result = _run_wasm("/tmp/test_arith.wasm")
    assert result.returncode == 0, f"wasmtime execution failed:\n{result.stderr}"

    lines = result.stdout.strip().splitlines()
    assert "10 + 3 = 13" in lines, f"Missing '10 + 3 = 13' in output:\n{result.stdout}"
    assert "10 * 3 = 30" in lines, f"Missing '10 * 3 = 30' in output:\n{result.stdout}"
    assert "10 ** 3 = 1000" in lines, f"Missing '10 ** 3 = 1000' in output:\n{result.stdout}"
    assert "10 % 3 = 1" in lines, f"Missing '10 % 3 = 1' in output:\n{result.stdout}"


def test_functions_loops_output():
    """Compiling functions_loops.sam runs correctly with factorial and fibonacci."""
    comp = _compile_to_wasm(SAMPLES / "functions_loops.sam", "/tmp/test_funcloop.wasm")
    assert comp.returncode == 0, f"Compilation failed:\n{comp.stderr}"
    _assert_real_wasm("/tmp/test_funcloop.wasm", min_reachable=2)

    result = _run_wasm("/tmp/test_funcloop.wasm")
    assert result.returncode == 0, f"wasmtime execution failed:\n{result.stderr}"

    lines = result.stdout.strip().splitlines()
    assert "5! = 120" in lines, f"Missing '5! = 120' in output:\n{result.stdout}"
    assert "8! = 40320" in lines, f"Missing '8! = 40320' in output:\n{result.stdout}"
    assert "fib(10) = 55" in lines, f"Missing 'fib(10) = 55' in output:\n{result.stdout}"
    assert "fib(15) = 610" in lines, f"Missing 'fib(15) = 610' in output:\n{result.stdout}"


def test_string_ops_output():
    """Compiling string_ops.sam runs correctly with string concat and building."""
    comp = _compile_to_wasm(SAMPLES / "string_ops.sam", "/tmp/test_strops.wasm")
    assert comp.returncode == 0, f"Compilation failed:\n{comp.stderr}"
    _assert_real_wasm("/tmp/test_strops.wasm", min_reachable=2)

    result = _run_wasm("/tmp/test_strops.wasm")
    assert result.returncode == 0, f"wasmtime execution failed:\n{result.stderr}"

    lines = result.stdout.strip().splitlines()
    assert "range: 1, 2, 3, 4, 5" in lines, f"Missing range output:\n{result.stdout}"
    assert "Hello WASM" in lines, f"Missing 'Hello WASM' in output:\n{result.stdout}"
    assert "repeat(abc, 3) = abcabcabc" in lines, f"Missing repeat output:\n{result.stdout}"


def test_logic_output():
    """Compiling logic.sam runs correctly with booleans and comparisons."""
    comp = _compile_to_wasm(SAMPLES / "logic.sam", "/tmp/test_logic.wasm")
    assert comp.returncode == 0, f"Compilation failed:\n{comp.stderr}"
    _assert_real_wasm("/tmp/test_logic.wasm", min_reachable=1)

    result = _run_wasm("/tmp/test_logic.wasm")
    assert result.returncode == 0, f"wasmtime execution failed:\n{result.stderr}"

    lines = result.stdout.strip().splitlines()
    assert "classify(5) = positive" in lines, f"Missing classify output:\n{result.stdout}"
    assert "classify(-3) = negative" in lines, f"Missing classify output:\n{result.stdout}"
    assert "classify(0) = zero" in lines, f"Missing classify output:\n{result.stdout}"
    assert "true and false = false" in lines, f"Missing boolean output:\n{result.stdout}"
    assert "not true = false" in lines, f"Missing not output:\n{result.stdout}"


def test_wasm_deterministic():
    """Compiling the same source twice produces identical .wasm output."""
    comp1 = _compile_to_wasm(SAMPLES / "hello.sam", "/tmp/test_det1.wasm")
    comp2 = _compile_to_wasm(SAMPLES / "hello.sam", "/tmp/test_det2.wasm")
    assert comp1.returncode == 0, f"First compile failed:\n{comp1.stderr}"
    assert comp2.returncode == 0, f"Second compile failed:\n{comp2.stderr}"

    bytes1 = Path("/tmp/test_det1.wasm").read_bytes()
    bytes2 = Path("/tmp/test_det2.wasm").read_bytes()
    assert bytes1 == bytes2, "Compiling the same source twice produced different .wasm files"


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
