import random
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

FILES = Path("/app/files") if Path("/app/files").exists() else Path(__file__).parents[1] / "files"
COMPILER = FILES / "compiler.py"


def compile_case(source):
    with tempfile.TemporaryDirectory() as tmp:
        sam, wasm = Path(tmp) / "generated.sam", Path(tmp) / "generated.wasm"
        sam.write_text(source)
        built = subprocess.run([sys.executable, str(COMPILER), "compile", str(sam), "-o", str(wasm),
                                "--target", "wasm32-wasi"], capture_output=True, text=True)
        assert built.returncode == 0, built.stderr
        run = subprocess.run(["wasmtime", str(wasm)], capture_output=True, text=True, timeout=10)
        dump = subprocess.run(["wasm-objdump", "-d", str(wasm)], capture_output=True, text=True, check=True).stdout
        return run, wasm.read_bytes(), dump


def generated(seed, outer, skipped):
    rng = random.Random(seed)
    bias = rng.randint(2, 30)
    source = f"""fn main() {{ let i = 0; let score = {bias}; loop {{ i += 1; if i == {skipped} {{ continue; }}
        let j = 0; loop {{ j += 1; if j == 3 {{ break; }} score += i * j; }}
        if i == {outer} {{ break; }} }} return score; }}"""
    expected = bias + sum(i * 3 for i in range(1, outer + 1) if i != skipped)
    return source, f"{expected}\n"


def test_generated_independent_oracle():
    for index in range(20):
        source, expected = generated(0x5A51 + index, 4 + index % 6, 1 + index % 3)
        result, _, _ = compile_case(source)
        assert result.returncode == 0
        assert result.stdout == expected


def test_metamorphic_alpha_rename_and_neutral_branch():
    source, expected = generated(900, 8, 2)
    changed = source.replace("score", "aggregate").replace("let i", "let cursor").replace(" i ", " cursor ")
    changed = changed.replace("return aggregate", "if false { return 999; } return aggregate")
    assert compile_case(source)[0].stdout == compile_case(changed)[0].stdout == expected


def test_short_circuit_nested_and_left_to_right():
    source = """fn main() { let x = 0; if (false && (1 % 0 == 0)) || (true || (1 % 0 == 0)) { x += 13; } return x; }"""
    result, _, dump = compile_case(source)
    assert result.returncode == 0 and result.stdout == "13\n"
    assert dump.count("if") >= 3


def test_single_literal_mutation_changes_runtime_and_artifact():
    one, expected_one = generated(441, 6, 2)
    two, expected_two = generated(441, 7, 2)
    run_one, wasm_one, _ = compile_case(one)
    run_two, wasm_two, _ = compile_case(two)
    assert expected_one != expected_two and wasm_one != wasm_two
    assert run_one.stdout == expected_one and run_two.stdout == expected_two


def test_structural_reachability_from_start():
    source, expected = generated(712, 7, 3)
    result, binary, dump = compile_case(source)
    assert result.stdout == expected
    assert binary[:4] == b"\x00asm"
    headers = list(re.finditer(r"(?m)^[0-9a-f]+\s+func\[(\d+)\](?:\s+<([^>]+)>)?:", dump))
    bodies = {}
    names = {}
    for index, header in enumerate(headers):
        function_id = int(header.group(1))
        end = headers[index + 1].start() if index + 1 < len(headers) else len(dump)
        bodies[function_id] = dump[header.end():end]
        names[header.group(2) or ""] = function_id
    assert "_start" in names
    reachable, pending = set(), [names["_start"]]
    while pending:
        function_id = pending.pop()
        if function_id in reachable:
            continue
        reachable.add(function_id)
        pending.extend(int(item) for item in re.findall(r"\bcall\s+(\d+)\b", bodies.get(function_id, "")))
    reachable_code = "\n".join(bodies[item] for item in reachable if item in bodies)
    for opcode in ("loop", "br", "i32.mul", "i32.add"):
        assert opcode in reachable_code, f"lowered {opcode} is not reachable from _start"


def test_early_return_through_two_loops():
    source = """fn seek(target) { let i = 0; loop { i += 1; let j = 0; loop { j += 1;
        if i * j == target { return i + j; } if j == 5 { break; } } if i == 9 { break; } } return 0; }
        fn main() { return seek(28); }"""
    assert compile_case(source)[0].stdout == "11\n"


def test_artifact_policy_and_scaffold_boundary():
    contract = tomllib.loads((FILES / "contract.toml").read_text())
    assert contract["policy"]["editable"] == ["lowering.py"]
    assert contract["limits"]["max_model_tokens"] == 96000
    assert contract["limits"]["wall_clock_seconds"] == 43200
    assert not (FILES / "lowering.py").is_symlink()
    assert {path.name for path in FILES.glob("*.py")} == {"compiler.py", "lowering.py", "tests.py"}
