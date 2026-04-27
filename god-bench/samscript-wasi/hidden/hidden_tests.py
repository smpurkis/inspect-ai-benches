import hashlib
import re
import subprocess
import tempfile
from pathlib import Path

SAMPLES = Path("/app/files/samples")
HIDDEN_SAMPLES = Path("/app/hidden/samples")


def _find_compiler() -> str:
    """Find the compiler binary — check common locations."""
    candidates = [
        "/app/samscript",
        "/app/target/release/samscript",
        "/app/compiler/samscript",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    if Path("/app/Cargo.toml").exists():
        result = subprocess.run(
            ["cargo", "build", "--release"],
            capture_output=True, text=True, cwd="/app", timeout=600,
        )
        assert result.returncode == 0, f"cargo build failed:\n{result.stderr[-3000:]}"
        if Path("/app/target/release/samscript").exists():
            return "/app/target/release/samscript"
    assert False, "Compiler binary not found"


def _compile_to_wasm(sam_file: Path, out_wasm: str, timeout: int = 120) -> subprocess.CompletedProcess:
    compiler = _find_compiler()
    return subprocess.run(
        [compiler, "compile", str(sam_file), "-o", out_wasm, "--target", "wasm32-wasi"],
        capture_output=True, text=True, timeout=timeout,
    )


def _run_wasm(wasm_file: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["wasmtime", wasm_file],
        capture_output=True, text=True, timeout=timeout,
    )


def _assert_real_wasm(wasm_file: str, *, min_reachable: int = 3) -> None:
    """Verify that _start transitively calls real compiled functions.

    Defends against "eval-and-embed" where the compiler runs the interpreter
    at compile time, embeds output, and optionally adds dead proof functions.
    This check traces the call graph from _start and verifies that reachable
    (non-dead) code contains real arithmetic and control flow.
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


def _assert_no_embedded_values(wasm_file: str, forbidden: list) -> None:
    """Check that computed numerical results are not pre-baked in the WASM binary.

    If a precise computed value (like "3.1414926535900345" from a pi estimation)
    appears as an ASCII string in the binary, it was computed at compile time
    and embedded — not computed at WASM runtime.
    """
    data = Path(wasm_file).read_bytes()
    for value in forbidden:
        if value.encode("ascii") in data:
            assert False, (
                f"Pre-computed value '{value}' found as literal string in WASM binary. "
                f"Numerical results must be computed at runtime, not embedded at compile time."
            )


def test_hidden_arithmetic_program():
    """Complex arithmetic program with factorials and exponentiation."""
    result = _compile_to_wasm(HIDDEN_SAMPLES / "wasm_arithmetic.sam", "/tmp/hidden_arith.wasm")
    assert result.returncode == 0, f"Compilation failed:\n{result.stderr}"
    _assert_real_wasm("/tmp/hidden_arith.wasm", min_reachable=2)
    _assert_no_embedded_values("/tmp/hidden_arith.wasm", ["3628800", "65536"])

    wasm_out = _run_wasm("/tmp/hidden_arith.wasm")
    assert wasm_out.returncode == 0, f"Execution failed:\n{wasm_out.stderr}"

    lines = wasm_out.stdout.strip().splitlines()
    assert "5! = 120" in lines, f"Missing '5! = 120' in output:\n{wasm_out.stdout}"
    assert "10! = 3628800" in lines, f"Missing '10! = 3628800' in output:\n{wasm_out.stdout}"
    assert "2 ** 16 = 65536" in lines, f"Missing '2 ** 16 = 65536' in output:\n{wasm_out.stdout}"


def test_hidden_all_features():
    """Program using functions, loops, conditionals, string building, and booleans."""
    result = _compile_to_wasm(HIDDEN_SAMPLES / "wasm_all_features.sam", "/tmp/hidden_all.wasm")
    assert result.returncode == 0, f"Compilation failed:\n{result.stderr}"
    _assert_real_wasm("/tmp/hidden_all.wasm", min_reachable=4)
    _assert_no_embedded_values("/tmp/hidden_all.wasm", [
        "2, 3, 5, 7, 11, 13, 17, 19, 23, 29",  # prime list built by loop
        "5, 4, 3, 2, 1",  # countdown built by loop
    ])

    wasm_out = _run_wasm("/tmp/hidden_all.wasm")
    assert wasm_out.returncode == 0, f"Execution failed:\n{wasm_out.stderr}"

    lines = wasm_out.stdout.strip().splitlines()
    assert "abs(-7) = 7" in lines, f"Missing 'abs(-7) = 7'"
    assert "max(3, 9) = 9" in lines, f"Missing 'max(3, 9) = 9'"
    assert "countdown: 5, 4, 3, 2, 1" in lines, f"Missing countdown output"
    assert "fib(0) = 0" in lines, f"Missing 'fib(0) = 0'"
    assert "fib(8) = 21" in lines, f"Missing 'fib(8) = 21'"
    assert "the answer is 42" in lines, f"Missing 'the answer is 42'"
    assert "SamScript v1 is running on WASM!" in lines, f"Missing WASM banner"


def test_hidden_spring_mass():
    """Damped spring-mass simulation with Euler integration."""
    result = _compile_to_wasm(HIDDEN_SAMPLES / "wasm_spring_mass.sam", "/tmp/hidden_spring.wasm")
    assert result.returncode == 0, f"Compilation failed:\n{result.stderr}"
    _assert_real_wasm("/tmp/hidden_spring.wasm", min_reachable=2)
    _assert_no_embedded_values("/tmp/hidden_spring.wasm", [
        "-1.5579217536268157",   # step 100 position
        "-0.5723341191714225",   # step 500 position
        "0.16288221764481955",   # step 1000 position
    ])

    wasm_out = _run_wasm("/tmp/hidden_spring.wasm", timeout=60)
    assert wasm_out.returncode == 0, f"Execution failed:\n{wasm_out.stderr}"

    lines = wasm_out.stdout.strip().splitlines()
    assert "=== Damped Spring-Mass Simulation ===" in lines, f"Missing header"
    assert "step 100: x = -1.5579217536268157" in lines, (
        f"Missing or wrong step 100 output:\n{wasm_out.stdout}"
    )
    assert "step 500: x = -0.5723341191714225" in lines, (
        f"Missing or wrong step 500 output:\n{wasm_out.stdout}"
    )
    assert "step 1000: x = 0.16288221764481955" in lines, (
        f"Missing or wrong step 1000 output:\n{wasm_out.stdout}"
    )
    assert "zero crossings: 10" in lines, f"Missing zero crossings:\n{wasm_out.stdout}"
    assert "initial energy: 20" in lines, f"Missing initial energy:\n{wasm_out.stdout}"


def test_hidden_numerical():
    """Numerical methods: Newton's sqrt, pi estimation, Taylor e, integration."""
    result = _compile_to_wasm(HIDDEN_SAMPLES / "wasm_numerical.sam", "/tmp/hidden_numer.wasm")
    assert result.returncode == 0, f"Compilation failed:\n{result.stderr}"
    _assert_real_wasm("/tmp/hidden_numer.wasm", min_reachable=2)
    _assert_no_embedded_values("/tmp/hidden_numer.wasm", [
        "3.1414926535900345",    # pi from 10000 Leibniz terms
        "2.7182818284590455",    # e from 20 Taylor terms
        "5.187377517639621",     # H(100) harmonic sum
        "1.414213562373095",     # sqrt(2) via Newton
    ])

    wasm_out = _run_wasm("/tmp/hidden_numer.wasm", timeout=60)
    assert wasm_out.returncode == 0, f"Execution failed:\n{wasm_out.stderr}"

    lines = wasm_out.stdout.strip().splitlines()
    assert "sqrt(2) = 1.414213562373095" in lines, (
        f"Missing or wrong sqrt(2):\n{wasm_out.stdout}"
    )
    assert "sqrt(9) = 3" in lines, f"Missing sqrt(9):\n{wasm_out.stdout}"
    assert "sqrt(144) = 12" in lines, f"Missing sqrt(144):\n{wasm_out.stdout}"
    assert "distance(3, 4) = 5" in lines, f"Missing distance:\n{wasm_out.stdout}"
    assert "pi (10000 terms) = 3.1414926535900345" in lines, (
        f"Missing or wrong pi estimate:\n{wasm_out.stdout}"
    )
    assert "e (20 terms) = 2.7182818284590455" in lines, (
        f"Missing or wrong e estimate:\n{wasm_out.stdout}"
    )
    assert "H(100) = 5.187377517639621" in lines, (
        f"Missing or wrong harmonic sum:\n{wasm_out.stdout}"
    )


def test_hidden_deterministic_multiple_runs():
    """Compiling the same source 3 times produces byte-identical .wasm files."""
    hashes = []
    for i in range(3):
        out_path = f"/tmp/hidden_det_{i}.wasm"
        comp = _compile_to_wasm(HIDDEN_SAMPLES / "wasm_all_features.sam", out_path, timeout=180)
        assert comp.returncode == 0, f"Compile run {i} failed:\n{comp.stderr}"
        h = hashlib.sha256(Path(out_path).read_bytes()).hexdigest()
        hashes.append(h)

    assert hashes[0] == hashes[1] == hashes[2], (
        f"Non-deterministic wasm output:\n  {hashes}"
    )
    _assert_real_wasm("/tmp/hidden_det_0.wasm", min_reachable=4)


def test_hidden_error_handling():
    """Division by zero produces a non-zero exit code or specific compile-time error."""
    # Sanity check: compiler must be able to compile a real program first
    sanity = _compile_to_wasm(SAMPLES / "arithmetic.sam", "/tmp/hidden_err_sanity.wasm")
    assert sanity.returncode == 0, (
        f"Compiler cannot compile arithmetic.sam — cannot test error handling:\n{sanity.stderr}"
    )
    _assert_real_wasm("/tmp/hidden_err_sanity.wasm", min_reachable=1)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sam", dir="/tmp", delete=False
    ) as f:
        f.write('fn main() {\n    let x = 1 / 0\n}\n')
        err_file = f.name

    comp = _compile_to_wasm(Path(err_file), "/tmp/hidden_error.wasm")
    if comp.returncode == 0:
        result = _run_wasm("/tmp/hidden_error.wasm")
        assert result.returncode != 0, (
            "Expected non-zero exit for division by zero in wasm"
        )
    else:
        # Compile-time detection of division by zero is acceptable,
        # but the error must specifically mention it
        stderr_lower = comp.stderr.lower()
        assert "division" in stderr_lower or "divide" in stderr_lower or "zero" in stderr_lower, (
            f"Compilation failed but error doesn't mention division by zero:\n{comp.stderr}"
        )

    Path(err_file).unlink(missing_ok=True)


def test_hidden_wasm_valid_binary():
    """All compiled .wasm files start with the correct magic bytes."""
    for sam_file in [SAMPLES / "hello.sam", SAMPLES / "arithmetic.sam",
                     HIDDEN_SAMPLES / "wasm_arithmetic.sam"]:
        out = f"/tmp/hidden_magic_{sam_file.stem}.wasm"
        comp = _compile_to_wasm(sam_file, out)
        assert comp.returncode == 0, f"Compilation of {sam_file.name} failed:\n{comp.stderr}"
        data = Path(out).read_bytes()
        assert data[:4] == b'\x00asm', (
            f"{sam_file.name}: output does not start with wasm magic bytes"
        )
        assert len(data) > 8, f"{sam_file.name}: wasm file suspiciously small ({len(data)} bytes)"

    # Structural check on arithmetic programs (hello.sam has no arithmetic)
    _assert_real_wasm("/tmp/hidden_magic_arithmetic.wasm", min_reachable=1)
    _assert_real_wasm("/tmp/hidden_magic_wasm_arithmetic.wasm", min_reachable=2)


def test_hidden_multiple_programs_correct():
    """Both sample programs produce correct output when compiled and run."""
    # hello.sam
    comp = _compile_to_wasm(SAMPLES / "hello.sam", "/tmp/hidden_multi_hello.wasm")
    assert comp.returncode == 0, f"hello.sam compilation failed:\n{comp.stderr}"
    result = _run_wasm("/tmp/hidden_multi_hello.wasm")
    assert result.returncode == 0, f"hello.wasm execution failed:\n{result.stderr}"
    assert result.stdout.strip() == "hello world", (
        f"hello.sam: expected 'hello world', got {result.stdout!r}"
    )

    # arithmetic.sam
    comp = _compile_to_wasm(SAMPLES / "arithmetic.sam", "/tmp/hidden_multi_arith.wasm")
    assert comp.returncode == 0, f"arithmetic.sam compilation failed:\n{comp.stderr}"
    _assert_real_wasm("/tmp/hidden_multi_arith.wasm", min_reachable=1)
    result = _run_wasm("/tmp/hidden_multi_arith.wasm")
    assert result.returncode == 0, f"arithmetic.wasm execution failed:\n{result.stderr}"
    lines = result.stdout.strip().splitlines()
    expected = ["10 + 3 = 13", "10 * 3 = 30", "10 ** 3 = 1000", "10 % 3 = 1"]
    for exp in expected:
        assert exp in lines, f"arithmetic.sam: missing '{exp}' in output"


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
